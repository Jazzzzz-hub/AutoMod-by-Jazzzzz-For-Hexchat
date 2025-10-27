# ============================================================
#  AutoMod by Jazzzzz - Final v1.0 (patched)
#  - Wildcard support for new rules (*word*)
#  - Direct QUOTE KICK for reliable kicks on Flatpak/Bahamut
#  - Per-channel protection, configurable unban time/messages
#  - Timestamped logs (automod_log.txt in same folder)
#  - Resets/regenerates configs on first load if configured
# ============================================================

import hexchat
import os
import re
import time
import json

__module_name__ = "AutoMod by Jazzzzz"
__module_version__ = "1.0 Powered by Jazzzzz"
__module_description__ = "Auto kick/ban with wildcards, reliable QUOTE KICK, per-channel protection"

# -------------------------
# Paths & files
# -------------------------
base_configdir = hexchat.get_info("configdir") or os.path.expanduser("~/.config/hexchat")
BASE_DIR = os.path.join(base_configdir, "addons")
if not os.path.isdir(BASE_DIR):
    os.makedirs(BASE_DIR, exist_ok=True)

BAD_NICKS_FILE = os.path.join(BASE_DIR, "bad_nicks.txt")
BAD_WORDS_FILE = os.path.join(BASE_DIR, "bad_words.txt")
PROTECTED_FILE = os.path.join(BASE_DIR, "protected_channels.txt")
SETTINGS_FILE = os.path.join(BASE_DIR, "automod_settings.json")
README_PATH = os.path.join(BASE_DIR, "AutoMod_README.txt")
LOG_FILE = os.path.join(BASE_DIR, "automod_log.txt")

# -------------------------
# Behavior flags
# -------------------------
RESET_CONFIGS = True  # reset/regenerate config files (you asked earlier)

# -------------------------
# Timers and defaults
# -------------------------
UNBAN_CHECK_MS = 60 * 1000
KICK_DELAY_MS = 700

DEFAULTS = {
    "UNBAN_MINUTES": 60,   # default 1 hour as requested
    "KICKMSG": "",
    "BANMSG": "",
    "FLOOD_COUNT": 6,
    "FLOOD_SECONDS": 5,
    "DEFAULT_BAN_MINUTES": 60
}

# -------------------------
# Runtime state
# -------------------------
settings = {}
bad_nick_rules = {}   # pattern -> (compiled, message, duration_minutes, is_wildcard)
bad_word_rules = {}
protected_channels = set()
active_bans = {}      # (chan_lower, mask) -> expiry_ts
flood_records = {}    # (chan_lower, nick_lower) -> [timestamps]
whitelist_nicks = set(["ChanServ", "NickServ"])

# -------------------------
# Logging & persistence
# -------------------------
def timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def log(msg):
    line = f"{timestamp()} - {msg}"
    try:
        hexchat.prnt(f"[AutoMod] {msg}")
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        log("Settings saved.")
    except Exception as e:
        log(f"Error saving settings: {e}")

def load_settings():
    global settings
    if RESET_CONFIGS:
        try:
            if os.path.exists(SETTINGS_FILE):
                os.remove(SETTINGS_FILE)
        except Exception:
            pass
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            settings = DEFAULTS.copy()
    else:
        settings = DEFAULTS.copy()
    for k, v in DEFAULTS.items():
        if k not in settings:
            settings[k] = v
    save_settings()

# -------------------------
# Rule file helpers
# -------------------------
def ensure_files_exist(reset=False):
    files = [BAD_NICKS_FILE, BAD_WORDS_FILE, PROTECTED_FILE]
    if reset:
        for fp in files:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except Exception:
                pass
    for fp in files:
        if not os.path.exists(fp):
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    if fp == BAD_NICKS_FILE:
                        f.write("# bad_nicks.txt - pattern :: message :: minutes(optional)\n")
                        f.write("# Use *wildcards* for new rules, e.g. *rambo* :: msg :: 60\n")
                    elif fp == BAD_WORDS_FILE:
                        f.write("# bad_words.txt - pattern :: message :: minutes(optional)\n")
                        f.write("# Use *wildcards* for new rules, e.g. *badword* :: msg :: 60\n")
                    elif fp == PROTECTED_FILE:
                        f.write("# protected_channels.txt - one channel per line (lowercase)\n")
            except Exception:
                pass

def parse_rule_line(line):
    parts = [p.strip() for p in line.split("::")]
    if not parts:
        return None
    pattern = parts[0] if len(parts) >= 1 else ""
    message = parts[1] if len(parts) >= 2 else ""
    duration = None
    if len(parts) >= 3:
        try:
            duration = int(parts[2])
        except:
            duration = None
    return pattern, message, duration

def pattern_to_regex(pat, is_new_rule=False):
    """
    Convert wildcard pattern to regex if '*' present and is_new_rule True.
    Otherwise try to compile as plain regex; on failure escape literal.
    Returns (compiled_regex, is_wildcard_bool)
    """
    if "*" in pat and is_new_rule:
        escaped = ""
        for ch in pat:
            if ch == "*":
                escaped += ".*"
            else:
                escaped += re.escape(ch)
        try:
            cre = re.compile(escaped, re.IGNORECASE)
            return cre, True
        except re.error:
            return None, False
    else:
        # Try compile as regex; if fails, escape literal
        try:
            cre = re.compile(pat, re.IGNORECASE)
            return cre, False
        except re.error:
            try:
                cre = re.compile(re.escape(pat), re.IGNORECASE)
                return cre, False
            except Exception:
                return None, False

def load_rules_from_file(filename):
    rules = {}
    if not os.path.exists(filename):
        return rules
    try:
        with open(filename, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parsed = parse_rule_line(line)
                if not parsed:
                    continue
                pat, msg, dur = parsed
                # Existing rules on disk: do NOT auto-convert plain strings to wildcard
                cre, is_wild = pattern_to_regex(pat, is_new_rule=False)
                if cre is None:
                    log(f"Invalid pattern skipped: {pat}")
                    continue
                rules[pat] = (cre, msg, dur, is_wild)
    except Exception as e:
        log(f"Error loading {filename}: {e}")
    return rules

def save_rules_to_file(rules, filename):
    try:
        with open(filename, "w", encoding="utf-8") as fh:
            for pat, (_, msg, dur, _) in rules.items():
                if dur is None:
                    fh.write(f"{pat} :: {msg}\n")
                else:
                    fh.write(f"{pat} :: {msg} :: {dur}\n")
        log(f"Saved {len(rules)} rules to {os.path.basename(filename)}")
    except Exception as e:
        log(f"Error saving rules: {e}")

def load_protected_channels(reset=False):
    global protected_channels
    protected_channels = set()
    if reset and os.path.exists(PROTECTED_FILE):
        try:
            os.remove(PROTECTED_FILE)
        except Exception:
            pass
    if os.path.exists(PROTECTED_FILE):
        try:
            with open(PROTECTED_FILE, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        protected_channels.add(s.lower())
        except Exception as e:
            log(f"Error loading protected channels: {e}")

def save_protected_channels():
    """Save protected channels to PROTECTED_FILE."""
    try:
        with open(PROTECTED_FILE, "w", encoding="utf-8") as f:
            for chan in sorted(protected_channels):
                f.write(chan + "\n")
        log("Protected channels saved.")
    except Exception as e:
        log(f"Error saving protected channels: {e}")

def load_all(reset=False):
    ensure_files_exist(reset=reset)
    load_settings()
    global bad_nick_rules, bad_word_rules
    bad_nick_rules = load_rules_from_file(BAD_NICKS_FILE)
    bad_word_rules = load_rules_from_file(BAD_WORDS_FILE)
    load_protected_channels(reset=reset)
    log(f"Loaded {len(bad_nick_rules)} nick rules, {len(bad_word_rules)} word rules, {len(protected_channels)} protected channels")

# -------------------------
# Scheduling helper
# -------------------------
def schedule_once(ms, func):
    def wrapper(userdata=None):
        try:
            func()
        except Exception as e:
            log(f"Scheduled function error: {e}")
        return False
    hexchat.hook_timer(ms, wrapper)

# -------------------------
# Ban/Kick/Unban with QUOTE KICK
# -------------------------
def ban_mask_for_nick(nick):
    return f"{nick}!*@*"

def apply_ban_and_kick(channel, nick, reason, duration_minutes):
    mask = ban_mask_for_nick(nick)
    cmd_ban = f"MODE {channel} +b {mask}"
    cmd_kick_quote = f"QUOTE KICK {channel} {nick} :{reason}"
    try:
        ctx = hexchat.find_context(channel=channel)
    except Exception:
        ctx = None

    try:
        if ctx:
            try:
                ctx.set()
            except Exception:
                pass
            ctx.command(cmd_ban)
        else:
            hexchat.command(cmd_ban)
    except Exception as e:
        log(f"Error issuing ban: {e}")

    def do_kick():
        try:
            hexchat.command(cmd_kick_quote)
            log(f"Sent QUOTE KICK {channel} {nick} :{reason}")
        except Exception as e:
            log(f"Failed QUOTE KICK {nick} in {channel}: {e}")

    schedule_once(KICK_DELAY_MS, do_kick)

    expiry = time.time() + (duration_minutes * 60 if duration_minutes else settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"]) * 60)
    active_bans[(channel.lower(), mask)] = expiry
    log(f"Set ban {mask} in {channel} (expires in {int((expiry-time.time())/60)} min) — reason: {reason}")

def unban_expired(userdata=None):
    now = time.time()
    removed = []
    for (chan, mask), expiry in list(active_bans.items()):
        if now >= expiry:
            cmd = f"MODE {chan} -b {mask}"
            try:
                ctx = hexchat.find_context(channel=chan)
            except Exception:
                ctx = None
            try:
                if ctx:
                    try:
                        ctx.set()
                    except Exception:
                        pass
                    ctx.command(cmd)
                else:
                    hexchat.command(cmd)
                log(f"Unbanned {mask} from {chan}")
            except Exception as e:
                log(f"Error unbanning {mask} from {chan}: {e}")
            removed.append((chan, mask))
    for key in removed:
        active_bans.pop(key, None)
    return True

# -------------------------
# Flood detection
# -------------------------
def record_message_for_flood(channel, nick):
    key = (channel.lower(), nick.lower())
    now = time.time()
    window = settings.get("FLOOD_SECONDS", DEFAULTS["FLOOD_SECONDS"])
    arr = [t for t in flood_records.get(key, []) if now - t <= window]
    arr.append(now)
    flood_records[key] = arr
    count = settings.get("FLOOD_COUNT", DEFAULTS["FLOOD_COUNT"])
    return len(arr) >= count

# -------------------------
# Event handlers
# -------------------------
def is_whitelisted(nick):
    return nick in whitelist_nicks

def is_protected(channel):
    return bool(channel) and channel.lower() in protected_channels

def on_join(word, word_eol, userdata):
    """
    Called when someone joins a channel.
    For wildcard nick rules (is_wild == True) we skip the rule if the nick
    exactly equals the wildcard core (e.g. pattern '*rambo*' -> core 'rambo').
    Otherwise apply the rule if the regex matches.
    """
    if len(word) < 1:
        return hexchat.EAT_NONE

    nick = word[0]
    channel = hexchat.get_info("channel")
    if not is_protected(channel):
        return hexchat.EAT_NONE
    if is_whitelisted(nick):
        return hexchat.EAT_NONE

    nick_l = nick.lower()

    for pat, (cre, msg, dur, is_wild) in bad_nick_rules.items():
        try:
            # If regex matches at all, consider it
            if not cre.search(nick):
                continue

            # If this rule was created as a wildcard, compute the "core"
            # and skip only when core exactly equals the nick (case-insensitive).
            if is_wild:
                # Remove all '*' and whitespace from the pattern to get core
                core = re.sub(r"\s+", "", pat)          # remove spaces
                core = re.sub(r"\*+", "*", core)       # compress consecutive '*'
                core = core.replace("*", "")           # remove wildcard chars
                core = core.strip().lower()
                if core:
                    if core == nick_l:
                        # Exact equality — skip wildcard rule (user requested)
                        log(f"Wildcard rule '{pat}' skipped for exact-match nick '{nick}'")
                        continue
                # if core is empty (pattern was just '*' or similar), do not skip
            # Not skipped — enforce rule
            reason = msg or settings.get("BANMSG", "") or "AutoMod: Prohibited nickname"
            apply_ban_and_kick(channel, nick, reason,
                               dur if (dur is not None) else settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"]))
            return hexchat.EAT_ALL
        except Exception as e:
            log(f"Error checking join rule '{pat}' against nick '{nick}': {e}")
            continue

    return hexchat.EAT_NONE

def on_message(word, word_eol, userdata):
    if len(word) < 2:
        return hexchat.EAT_NONE
    nick = word[0]
    message = word_eol[1] if len(word_eol) > 1 else word[1]
    channel = hexchat.get_info("channel")
    if not is_protected(channel):
        return hexchat.EAT_NONE
    if is_whitelisted(nick):
        return hexchat.EAT_NONE

    if record_message_for_flood(channel, nick):
        reason = settings.get("KICKMSG", "") or settings.get("BANMSG", "") or "Flooding the channel"
        apply_ban_and_kick(channel, nick, reason, settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"]))
        flood_records.pop((channel.lower(), nick.lower()), None)
        return hexchat.EAT_ALL

    for pat, (cre, msg, dur, is_wild) in bad_word_rules.items():
        if cre.search(message):
            reason = msg or settings.get("BANMSG", "") or "AutoMod: Prohibited language"
            apply_ban_and_kick(channel, nick, reason, dur if dur is not None else settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"]))
            return hexchat.EAT_ALL

    return hexchat.EAT_NONE

# -------------------------
# Commands
# -------------------------
def cmd_reload(word, word_eol, userdata):
    load_all(reset=RESET_CONFIGS)
    log("Rules & settings reloaded.")
    return hexchat.EAT_ALL

def cmd_list(word, word_eol, userdata):
    hexchat.prnt("=== AutoMod Rules & Settings ===")
    hexchat.prnt(f"Protected channels: {', '.join(sorted(protected_channels)) or '<none>'}")
    hexchat.prnt(f"Settings: UNBAN_MINUTES={settings.get('UNBAN_MINUTES')}, FLOOD={settings.get('FLOOD_COUNT')} msgs/{settings.get('FLOOD_SECONDS')}s")
    hexchat.prnt("-- Bad Nicks --")
    for pat, (_, msg, dur, _) in bad_nick_rules.items():
        hexchat.prnt(f"{pat} :: {msg} :: {dur if dur is not None else settings.get('UNBAN_MINUTES') }m")
    hexchat.prnt("-- Bad Words --")
    for pat, (_, msg, dur, _) in bad_word_rules.items():
        hexchat.prnt(f"{pat} :: {msg} :: {dur if dur is not None else settings.get('UNBAN_MINUTES') }m")
    hexchat.prnt("===============================")
    return hexchat.EAT_ALL

def cmd_add(word, word_eol, userdata):
    if len(word) < 3:
        hexchat.prnt("Usage: /AMADD <nick|word> pattern::message::minutes?")
        return hexchat.EAT_ALL
    kind = word[1].lower()
    entry = " ".join(word[2:]).strip()
    parsed = parse_rule_line(entry)
    if not parsed:
        hexchat.prnt("Invalid rule format. Use: pattern :: message :: minutes(optional)")
        return hexchat.EAT_ALL
    pat, msg, dur = parsed
    # For new rules: if contains * treat as wildcard and convert
    is_new_wild = ("*" in pat)
    cre, is_wild = pattern_to_regex(pat, is_new_rule=is_new_wild)
    if cre is None:
        hexchat.prnt("Invalid regex/pattern.")
        return hexchat.EAT_ALL
    if kind == "nick":
        bad_nick_rules[pat] = (cre, msg, dur, is_wild)
        save_rules_to_file(bad_nick_rules, BAD_NICKS_FILE)
        hexchat.prnt(f"Added nick rule: {pat}")
    elif kind == "word":
        bad_word_rules[pat] = (cre, msg, dur, is_wild)
        save_rules_to_file(bad_word_rules, BAD_WORDS_FILE)
        hexchat.prnt(f"Added word rule: {pat}")
    else:
        hexchat.prnt("Type must be 'nick' or 'word'.")
    return hexchat.EAT_ALL

def cmd_del(word, word_eol, userdata):
    if len(word) < 3:
        hexchat.prnt("Usage: /AMDEL <nick|word> <pattern>")
        return hexchat.EAT_ALL
    kind = word[1].lower()
    pat = " ".join(word[2:]).strip()
    rules = bad_nick_rules if kind == "nick" else bad_word_rules if kind == "word" else None
    if rules is None:
        hexchat.prnt("Type must be 'nick' or 'word'.")
        return hexchat.EAT_ALL
    if pat in rules:
        rules.pop(pat, None)
        save_rules_to_file(rules, BAD_NICKS_FILE if kind == "nick" else BAD_WORDS_FILE)
        hexchat.prnt(f"Removed {kind} rule: {pat}")
    else:
        hexchat.prnt("Pattern not found.")
    return hexchat.EAT_ALL

def cmd_chan(word, word_eol, userdata):
    if len(word) < 2:
        hexchat.prnt("Usage: /AMCHAN <#channel>")
        return hexchat.EAT_ALL
    ch = word[1].strip().lower()
    if not ch.startswith("#"):
        hexchat.prnt("Channel must start with #")
        return hexchat.EAT_ALL
    if ch in protected_channels:
        protected_channels.remove(ch)
        hexchat.prnt(f"Removed protection: {ch}")
    else:
        protected_channels.add(ch)
        hexchat.prnt(f"Added protection: {ch}")
    save_protected_channels()
    return hexchat.EAT_ALL
# --- Remove Protected Channel Command ---
def cmd_unchan(word, word_eol, userdata):
    """Usage: /AMUNCHAN #channel — Remove a protected channel"""
    if len(word) < 2:
        hexchat.prnt("[AutoMod] Usage: /AMUNCHAN #channel")
        return hexchat.EAT_ALL

    channel = word[1].lower()

    if channel in protected_channels:
        protected_channels.remove(channel)
        save_protected_channels()
        hexchat.prnt(f"[AutoMod] Removed protection: {channel}")
    else:
        hexchat.prnt(f"[AutoMod] Channel not in protection list: {channel}")

    return hexchat.EAT_ALL

hexchat.hook_command("AMUNCHAN", cmd_unchan, help="/AMUNCHAN #channel — Remove channel from AutoMod protection")

def cmd_set(word, word_eol, userdata):
    if len(word) < 2:
        hexchat.prnt("Usage: /AMSET <UNBAN_MINUTES|KICKMSG|BANMSG|FLOOD|DEFAULTBAN> args...")
        return hexchat.EAT_ALL
    opt = word[1].upper()
    if opt == "UNBAN_MINUTES" and len(word) >= 3:
        try:
            val = int(word[2])
            settings["UNBAN_MINUTES"] = val
            save_settings()
            hexchat.prnt(f"UNBAN_MINUTES set to {val}")
        except:
            hexchat.prnt("Invalid number.")
    elif opt == "KICKMSG" and len(word) >= 3:
        msg = " ".join(word[2:])
        settings["KICKMSG"] = msg
        save_settings()
        hexchat.prnt("KICKMSG updated.")
    elif opt == "BANMSG" and len(word) >= 3:
        msg = " ".join(word[2:])
        settings["BANMSG"] = msg
        save_settings()
        hexchat.prnt("BANMSG updated.")
    elif opt == "FLOOD" and len(word) >= 4:
        try:
            cnt = int(word[2]); secs = int(word[3])
            settings["FLOOD_COUNT"] = cnt
            settings["FLOOD_SECONDS"] = secs
            save_settings()
            hexchat.prnt(f"FLOOD set to {cnt} msgs/{secs}s")
        except:
            hexchat.prnt("Invalid numbers.")
    elif opt == "DEFAULTBAN" and len(word) >= 3:
        try:
            val = int(word[2])
            settings["DEFAULT_BAN_MINUTES"] = val
            save_settings()
            hexchat.prnt(f"DEFAULT_BAN_MINUTES set to {val}")
        except:
            hexchat.prnt("Invalid number.")
    else:
        hexchat.prnt("Unknown AMSET option or missing args.")
    return hexchat.EAT_ALL

def cmd_gui(word, word_eol, userdata):
    if len(word) < 2 or word[1].lower() not in ("nick", "word"):
        hexchat.prnt("Usage: /AMGUI <nick|word>")
        return hexchat.EAT_ALL
    kind = word[1].lower()
    hexchat.command(f'GUI MSGBOX "Enter rule as: pattern :: message :: minutes(optional)\\nThen run: /AMADD {kind} <rule>" "AutoMod" 1')
    hexchat.prnt(f"After closing the popup, run: /AMADD {kind} pattern :: message :: minutes(optional)")
    return hexchat.EAT_ALL

def cmd_help(word, word_eol, userdata):
    help_lines = [
        "AutoMod Help:",
        "/AMMENU         Show text menu",
        "/AMHELP         Show this help",
        "/AMLIST         List rules & channels",
        "/AMADD          Add rule: /AMADD <nick|word> pattern::message::minutes?",
        "/AMDEL          Delete rule: /AMDEL <nick|word> pattern",
        "/AMCHAN         Toggle protection for a channel",
        "/AMUNCHAN       Toggle remove protection for a channel",
        "/AMSET UNBAN_MINUTES <n>   Set auto-unban minutes",
        "/AMSET KICKMSG <text>      Set default kick message",
        "/AMSET BANMSG <text>       Set default ban message",
        "/AMSET FLOOD <count> <s>   Configure flood detection",
        "/AUTORELOAD     Reload rules and settings",
    ]
    for l in help_lines:
        hexchat.prnt(l)
    return hexchat.EAT_ALL

def show_text_menu(word=None, word_eol=None, userdata=None):
    lines = [
        "────────── AutoMod by Jazzzzz ──────────",
        "1) Add Bad Nick    -> /AMADD nick <pattern>::<message>::<minutes?>",
        "2) Add Bad Word    -> /AMADD word <pattern>::<message>::<minutes?>",
        "3) List Rules      -> /AMLIST",
        "4) Delete Rule     -> /AMDEL <nick|word> <pattern>",
        "5) Toggle Protect  -> /AMCHAN #channel",
        "6) Flood Settings  -> /AMSET FLOOD <count> <seconds>",
        "7) Default Ban     -> /AMSET DEFAULTBAN <minutes>",
        "8) Reload Rules    -> /AUTORELOAD",
        "9) Quick Help      -> /AMHELP",
        "10) Del Chan Prot  -> /AMUNCHAN #channel",
        "───────────────────────────────────────",
    ]
    for l in lines:
        hexchat.prnt(l)
    return hexchat.EAT_ALL

# -------------------------
# Init & hooks
# -------------------------
load_all(reset=RESET_CONFIGS)
hexchat.hook_timer(UNBAN_CHECK_MS, unban_expired)
hexchat.hook_print("Join", on_join)
hexchat.hook_print("Channel Message", on_message)

hexchat.hook_command("AUTORELOAD", cmd_reload)
hexchat.hook_command("AMLIST", cmd_list)
hexchat.hook_command("AMADD", cmd_add)
hexchat.hook_command("AMDEL", cmd_del)
hexchat.hook_command("AMCHAN", cmd_chan)
hexchat.hook_command("AMUNCHAN", cmd_chan)
hexchat.hook_command("AMSET", cmd_set)
hexchat.hook_command("AMGUI", cmd_gui)
hexchat.hook_command("AMHELP", cmd_help)
hexchat.hook_command("AMMENU", show_text_menu)

show_text_menu()
if os.path.exists(README_PATH):
    log(f"Documentation: {README_PATH}")
else:
    log("README not found in addons folder.")
log(f"{__module_name__} v{__module_version__} loaded. Protected: {', '.join(sorted(protected_channels)) or '<none>'}")

# End of script
