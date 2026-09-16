AniToon hotfix

Replace only:
plugins/cancel.py
plugins/file_action_fix.py
plugins/rename_reply_responder.py

Fixes:
- Cancel callback and /cancel stop the actual processing task.
- Rename now always shows Convert into File / Convert into Video.
- The exact rename UI/prompt messages are cleaned without touching unrelated messages.
- Existing video pipeline from current GitHub version is retained in file_action_fix.py.
