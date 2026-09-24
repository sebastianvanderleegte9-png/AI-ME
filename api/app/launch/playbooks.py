"""Launch playbooks (Component 8). Each is a list of tasks relative to launch day (T-42 ... T+7).
A task becomes a Job(type=launch_task) or, for content, a Job(type=post) drafted by the voice
engine so it lands in the same approval feed. Versioned like everything else.

Fields: day (offset from launch), kind (task|post|asset|outreach), title, detail, channel?, format?"""

PH_V1 = [
    # T-6w: decide
    {"day": -42, "kind": "task", "title": "Pick the one thing", "detail": "One feature, one segment, one hook. If the hook needs a paragraph, it is not the hook."},
    {"day": -42, "kind": "task", "title": "Set the number", "detail": "Target signups on launch day and in launch week. Write it in the brief."},
    {"day": -40, "kind": "asset", "title": "Landing page for the launch", "detail": "One page: hook, 60-second demo, three proof points, signup with the source field. Page factory template: use_case_with_data."},
    # T-5w to T-3w: warm up
    {"day": -35, "kind": "post", "title": "Teaser 1: the problem", "channel": "linkedin", "format": "contrarian_take", "detail": "Why the old way is wrong. No product mention."},
    {"day": -33, "kind": "post", "title": "Teaser 1 (X)", "channel": "x", "format": "contrarian_take", "detail": "Same claim, X length."},
    {"day": -28, "kind": "outreach", "title": "Line up 20 supporters", "detail": "Customers, design partners, peers who will comment and share on the day. Ask now, remind at T-1."},
    {"day": -28, "kind": "post", "title": "Build log 1", "channel": "linkedin", "format": "build_log", "detail": "What you are building and what broke."},
    {"day": -21, "kind": "outreach", "title": "Hunter", "detail": "Ask a hunter with relevant followers, or self-hunt. Confirm by T-14."},
    {"day": -21, "kind": "post", "title": "Customer story", "channel": "linkedin", "format": "customer_story", "detail": "The strongest proof point, told plainly."},
    {"day": -21, "kind": "asset", "title": "Gallery images (5) + 60s video", "detail": "Visual engine: number card, before/after, steps. Video: screen recording, no music, captions."},
    # T-2w: lock
    {"day": -14, "kind": "task", "title": "Freeze the product", "detail": "Nothing new ships between now and launch. Fix only."},
    {"day": -14, "kind": "asset", "title": "PH listing copy", "detail": "Tagline (60 chars), description, first comment (the founder's story, 200-300 words), FAQ."},
    {"day": -10, "kind": "post", "title": "Number with lesson", "channel": "x", "format": "number_with_lesson", "detail": "One number from the build."},
    {"day": -7, "kind": "post", "title": "Prediction", "channel": "linkedin", "format": "prediction", "detail": "Where this category goes; why now."},
    {"day": -7, "kind": "task", "title": "Schedule launch-day posts", "detail": "Approve every launch-day post now; nothing is written on the day."},
    {"day": -3, "kind": "outreach", "title": "Remind supporters", "detail": "Send the link and the exact time. Ask for a comment, not an upvote."},
    {"day": -1, "kind": "task", "title": "Dry run", "detail": "Open the listing, the page, the signup, the source field. Time zone check: PH resets 12:01am PT."},
    # Launch day
    {"day": 0, "kind": "post", "title": "Launch post", "channel": "linkedin", "format": "build_log", "detail": "We shipped. Here is what it does and the number we are chasing. Link."},
    {"day": 0, "kind": "post", "title": "Launch thread", "channel": "x", "format": "list", "detail": "5 things it does, each one line, link at the end."},
    {"day": 0, "kind": "task", "title": "Reply to every comment within 30 min", "detail": "All day. The attention map reply list is paused; this is the reply list today."},
    {"day": 0, "kind": "task", "title": "Ship one fix during the day", "detail": "Post it: 'someone asked for X, it is live'. Builds on the day."},
    # Follow-through
    {"day": 1, "kind": "post", "title": "Day-after numbers", "channel": "x", "format": "number_with_lesson", "detail": "Signups, upvotes, what surprised you."},
    {"day": 3, "kind": "post", "title": "Mistake", "channel": "linkedin", "format": "mistake", "detail": "What went wrong on the day and what you changed."},
    {"day": 7, "kind": "task", "title": "Close the launch", "detail": "Results into the launch record: signups by source, impressions in ICP, upvotes. What to keep for next time."},
]

FEATURE_DROP_V1 = [
    {"day": -14, "kind": "task", "title": "Pick the one thing", "detail": "One feature, one segment, one hook."},
    {"day": -14, "kind": "asset", "title": "Feature page", "detail": "Page factory: use_case_with_data for this feature."},
    {"day": -10, "kind": "post", "title": "Problem teaser", "channel": "linkedin", "format": "contrarian_take", "detail": "The problem, no product."},
    {"day": -7, "kind": "post", "title": "Build log", "channel": "x", "format": "build_log", "detail": "What you are building."},
    {"day": -3, "kind": "outreach", "title": "Tell 10 customers first", "detail": "Direct message the customers who asked for it. Ask for a screenshot on the day."},
    {"day": 0, "kind": "post", "title": "It's live", "channel": "linkedin", "format": "customer_story", "detail": "Who asked, what shipped, one number."},
    {"day": 0, "kind": "post", "title": "It's live (X)", "channel": "x", "format": "number_with_lesson", "detail": "One line, one number, link."},
    {"day": 2, "kind": "post", "title": "How it works", "channel": "linkedin", "format": "framework", "detail": "3-5 steps."},
    {"day": 7, "kind": "task", "title": "Close", "detail": "Results into the launch record."},
]

JOINT_V1 = [
    {"day": -28, "kind": "outreach", "title": "Agree the joint hook with the partner", "detail": "One sentence both companies say. Split the audience: who posts what, when."},
    {"day": -21, "kind": "asset", "title": "Shared asset", "detail": "One page or one tool both link to; both logos; the source field on both signups."},
    {"day": -14, "kind": "post", "title": "Cross-post 1", "channel": "linkedin", "format": "customer_story", "detail": "Each founder tells the other's customer story."},
    {"day": -7, "kind": "post", "title": "Cross-post 2", "channel": "x", "format": "question", "detail": "Both ask the same question to their ICPs."},
    {"day": 0, "kind": "post", "title": "Joint launch post", "channel": "linkedin", "format": "build_log", "detail": "Both post within the same hour, tagging each other."},
    {"day": 0, "kind": "post", "title": "Joint launch (X)", "channel": "x", "format": "list", "detail": "Thread; partner quote-tweets."},
    {"day": 7, "kind": "task", "title": "Close and share results with partner", "detail": "Both launch records get the combined numbers."},
]

PLAYBOOKS = {"product_hunt": ("ph-v1", PH_V1), "feature_drop": ("drop-v1", FEATURE_DROP_V1),
             "joint": ("joint-v1", JOINT_V1), "customer_story": ("drop-v1", FEATURE_DROP_V1)}
