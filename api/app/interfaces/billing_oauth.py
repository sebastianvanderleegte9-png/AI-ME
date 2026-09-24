"""Billing (Stripe) and OAuth (LinkedIn, X) behind interfaces with fakes (Component 14).
Tokens are encrypted with Fernet before they touch the database."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx


# ---------- billing ----------
PLANS = {"founder": {"name": "Founder", "monthly_usd": 500}, "team": {"name": "Team", "monthly_usd": 1500},
         "growth": {"name": "Growth", "monthly_usd": 5000}}


@dataclass
class CheckoutSession:
    url: str
    session_ref: str


@dataclass
class BillingEvent:
    kind: str                 # checkout.completed | subscription.updated | subscription.deleted | invoice.failed
    customer_ref: str | None
    subscription_ref: str | None
    plan: str | None
    status: str | None        # active | past_due | canceled | trialing | paused
    company_id: str | None    # from metadata
    period_end: float | None = None


class Billing(ABC):
    @abstractmethod
    def create_checkout(self, *, company_id: str, email: str, plan: str, success_url: str, cancel_url: str) -> CheckoutSession: ...

    @abstractmethod
    def parse_webhook(self, headers: dict, body: bytes) -> BillingEvent | None: ...

    @abstractmethod
    def portal_url(self, *, customer_ref: str, return_url: str) -> str: ...


class FakeBilling(Billing):
    def __init__(self):
        self.sessions: dict[str, dict] = {}

    def create_checkout(self, *, company_id, email, plan, success_url, cancel_url):
        ref = f"cs_fake_{secrets.token_hex(6)}"
        self.sessions[ref] = {"company_id": company_id, "email": email, "plan": plan}
        return CheckoutSession(url=f"{success_url}?session={ref}&fake=1", session_ref=ref)

    def parse_webhook(self, headers, body):
        ev = json.loads(body or b"{}")
        return BillingEvent(kind=ev.get("kind", "checkout.completed"), customer_ref=ev.get("customer_ref", "cus_fake"),
                            subscription_ref=ev.get("subscription_ref", "sub_fake"), plan=ev.get("plan"),
                            status=ev.get("status", "active"), company_id=ev.get("company_id"), period_end=ev.get("period_end"))

    def portal_url(self, *, customer_ref, return_url):
        return f"{return_url}?portal=fake"


class StripeBilling(Billing):
    def __init__(self, secret_key: str, webhook_secret: str, price_ids: dict[str, str]):
        self.key, self.whsec, self.prices = secret_key, webhook_secret, price_ids
        self._c = httpx.Client(base_url="https://api.stripe.com/v1", auth=(secret_key, ""), timeout=20)

    def create_checkout(self, *, company_id, email, plan, success_url, cancel_url):
        r = self._c.post("/checkout/sessions", data={
            "mode": "subscription", "customer_email": email, "line_items[0][price]": self.prices[plan], "line_items[0][quantity]": 1,
            "success_url": success_url + "?session={CHECKOUT_SESSION_ID}", "cancel_url": cancel_url,
            "metadata[company_id]": company_id, "metadata[plan]": plan, "subscription_data[metadata][company_id]": company_id,
            "subscription_data[metadata][plan]": plan})
        r.raise_for_status()
        j = r.json()
        return CheckoutSession(url=j["url"], session_ref=j["id"])

    def parse_webhook(self, headers, body):
        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature", "")
        parts = dict(p.split("=", 1) for p in sig.split(",") if "=" in p)
        payload = f"{parts.get('t')}.{body.decode()}"
        expected = hmac.new(self.whsec.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(parts.get("v1", ""), expected) or abs(time.time() - int(parts.get("t", 0))) > 300:
            return None
        ev = json.loads(body)
        obj = ev["data"]["object"]
        t = ev["type"]
        meta = obj.get("metadata") or {}
        kind = {"checkout.session.completed": "checkout.completed", "customer.subscription.updated": "subscription.updated",
                "customer.subscription.deleted": "subscription.deleted", "invoice.payment_failed": "invoice.failed"}.get(t)
        if not kind:
            return None
        return BillingEvent(kind=kind, customer_ref=obj.get("customer"), subscription_ref=obj.get("subscription") or obj.get("id"),
                            plan=meta.get("plan"), status=obj.get("status"), company_id=meta.get("company_id"),
                            period_end=obj.get("current_period_end"))

    def portal_url(self, *, customer_ref, return_url):
        r = self._c.post("/billing_portal/sessions", data={"customer": customer_ref, "return_url": return_url})
        r.raise_for_status()
        return r.json()["url"]


# ---------- oauth ----------
@dataclass
class OAuthResult:
    platform: str
    handle: str
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    scopes: list[str] = field(default_factory=list)


class OAuth(ABC):
    @abstractmethod
    def authorize_url(self, *, platform: str, state: str, redirect_uri: str) -> str: ...

    @abstractmethod
    def exchange(self, *, platform: str, code: str, redirect_uri: str, verifier: str | None = None) -> OAuthResult: ...


class FakeOAuth(OAuth):
    def authorize_url(self, *, platform, state, redirect_uri):
        return f"{redirect_uri}?state={state}&code=fake-{platform}-code"

    def exchange(self, *, platform, code, redirect_uri, verifier=None):
        return OAuthResult(platform=platform, handle=f"fake_{platform}_user", access_token=f"tok-{platform}-{secrets.token_hex(4)}",
                           refresh_token="rt", expires_in=3600 * 24 * 60, scopes=["w_member_social"] if platform == "linkedin" else ["tweet.write", "tweet.read", "users.read"])


class RealOAuth(OAuth):
    """LinkedIn (OAuth 2, 3-legged) and X (OAuth 2 with PKCE). Client ids/secrets from settings."""
    def __init__(self, linkedin: tuple[str, str] | None, x: tuple[str, str] | None):
        self.li, self.x = linkedin, x

    def authorize_url(self, *, platform, state, redirect_uri):
        if platform == "linkedin":
            return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode({
                "response_type": "code", "client_id": self.li[0], "redirect_uri": redirect_uri, "state": state,
                "scope": "openid profile w_member_social"})
        return "https://twitter.com/i/oauth2/authorize?" + urlencode({
            "response_type": "code", "client_id": self.x[0], "redirect_uri": redirect_uri, "state": state,
            "scope": "tweet.read tweet.write users.read offline.access", "code_challenge": "challenge", "code_challenge_method": "plain"})

    def exchange(self, *, platform, code, redirect_uri, verifier=None):
        if platform == "linkedin":
            r = httpx.post("https://www.linkedin.com/oauth/v2/accessToken", data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                "client_id": self.li[0], "client_secret": self.li[1]}, timeout=20)
            r.raise_for_status()
            j = r.json()
            me = httpx.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {j['access_token']}"}, timeout=20).json()
            return OAuthResult("linkedin", me.get("sub", ""), j["access_token"], j.get("refresh_token"), j.get("expires_in"), j.get("scope", "").split())
        r = httpx.post("https://api.twitter.com/2/oauth2/token", auth=(self.x[0], self.x[1]), data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier or "challenge"}, timeout=20)
        r.raise_for_status()
        j = r.json()
        me = httpx.get("https://api.twitter.com/2/users/me", headers={"Authorization": f"Bearer {j['access_token']}"}, timeout=20).json()
        return OAuthResult("x", (me.get("data") or {}).get("username", ""), j["access_token"], j.get("refresh_token"), j.get("expires_in"), j.get("scope", "").split())


# ---------- token encryption ----------
def cipher(key: str):
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)
