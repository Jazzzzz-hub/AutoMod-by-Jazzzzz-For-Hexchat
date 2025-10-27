──────────────────────────────────────────────
🔮 AutoMod by Jazzzzz — HexChat Moderator Script
Version: v1.0 (WildBan Edition)
──────────────────────────────────────────────

AutoMod is a Python-based moderation system for HexChat that automatically detects and bans/kicks users with invalid nicks, offensive words, or unwanted behavior. It also includes configurable timers, logging, and wildcard-based nickname detection.

──────────────────────────────────────────────
📦 INSTALLATION
──────────────────────────────────────────────

1. Make sure you have the **Flatpak version** of HexChat installed.

2. Locate your HexChat addons folder:

   ```
   ~/.var/app/io.github.Hexchat/config/hexchat/addons/
   ```

3. Copy the file `auto_mod_final_v1.0_wildban.py` into that folder.

4. Restart HexChat, or load manually using:

   ```
   /py load auto_mod_final_v1.0_wildban.py
   ```

5. You should see:

   ```
   [AutoMod] AutoMod by Jazzzzz v1.0 loaded. Protected: <none>
   ```

──────────────────────────────────────────────
⚙️ CONFIGURATION FILES
──────────────────────────────────────────────
AutoMod automatically creates and manages the following files in the addons folder:

* `badnicks.txt` — List of nickname rules
* `badwords.txt` — List of banned words
* `protected_channels.txt` — List of channels under AutoMod protection
* `automod_config.json` — Stores your ban timers and options
* `automod_log.txt` — Timestamped moderation log file

All data is **persistent** between restarts.

──────────────────────────────────────────────
💬 MAIN COMMANDS
──────────────────────────────────────────────

▶️ **Add Nick Rule**

```
/AMADD nick <nickname>::<reason>::<minutes>
```

* Example:

  ```
  /AMADD nick rambo::Invalid nick::60
  ```

  Wildcards (`*rambo*`) are automatically applied for **new rules**, meaning “any nickname containing ‘rambo’” will trigger.

---

▶️ **Add Word Rule**

```
/AMADD word <word>::<reason>::<minutes>
```

* Example:

  ```
  /AMADD word fuck::Please avoid swearing::30
  ```

---

▶️ **Protect a Channel**

```
/AMCHAN #channel
```

Adds the specified channel to AutoMod’s protection list.
Example:

```
/AMCHAN #testroom
```

---

▶️ **View Current Settings**

```
/AMLIST
```

Displays all current rules and protected channels.

---

▶️ **Remove a Rule**

```
/AMDEL nick <nickname>
/AMDEL word <word>
```

---

▶️ **Manual Ban / Kick**

```
/AMBAN <nick> <reason>
```

Instantly bans and kicks a user manually, using the same logic as AutoMod.

---

▶️ **Backup Configuration**

```
/AMBACKUP
```

Creates a full backup (rules + configs + channels) into:

```
addons/backups/AutoMod_backup_<date>.zip
```

──────────────────────────────────────────────
🧠 AUTO ACTIONS
──────────────────────────────────────────────

When a user joins a protected channel:

* If their nick matches a bad-nick rule → AutoMod sets a ban (`+b`) and kicks them.
* If they say a banned word → AutoMod sets a ban and kicks them.
* Bans automatically expire after the configured number of minutes.

**Note:**
Wildcard nick rules (like `*rambo*`) match any nick *containing* “rambo” — but **exact matches are ignored** (e.g. “Rambo” itself is safe).

──────────────────────────────────────────────
📄 LOGGING
──────────────────────────────────────────────

All actions are logged in:

```
automod_log.txt
```

Format:

```
[2025-10-27 15:25] [#testroom] KICK Rambo (invalid nick) — banned for 60 minutes
```

──────────────────────────────────────────────
🔧 TROUBLESHOOTING
──────────────────────────────────────────────

If you ever need to reset everything:

1. Close HexChat.
2. Delete:

   ```
   badnicks.txt
   badwords.txt
   protected_channels.txt
   automod_config.json
   ```
3. Restart HexChat — files will regenerate empty.

──────────────────────────────────────────────
🛡️ ADMIN-ONLY SETUP (Optional)
──────────────────────────────────────────────

To restrict who can control AutoMod (e.g. only you or trusted ops):

1. Open your `auto_mod_final_v1.0_wildban.py` file in a text editor.
2. Find the line near the top that looks like:

   ```python
   ADMINS = []
   ```
3. Add your authorized nicks inside it, for example:

   ```python
   ADMINS = ["Jazzzzz", "DarkStar", "rambo"]
   ```
4. Save the file and reload:

   ```
   /py reload auto_mod_final_v1.0_wildban.py
   ```

Now, only those nicknames will be able to run `/AMADD`, `/AMDEL`, `/AMCHAN`, `/AMBACKUP`, etc.
Everyone else will see:

```
[AutoMod] Permission denied — admin only command.
```

──────────────────────────────────────────────
💜 CREDIT
──────────────────────────────────────────────
Developed & tuned by **Jazzzzz**
Tested on Ubuntu (Flatpak HexChat)
Special thanks to all who kept IRC alive ✨

──────────────────────────────────────────────

