# ============================================================
#  AutoMod by Jazzzzz - Final v1.0 (patched)
#  - Wildcard support for new rules (*word*)
#  - Direct QUOTE KICK for reliable kicks on Flatpak/Bahamut
#  - Per-channel protection, configurable unban time/messages
#  - Timestamped logs (automod_log.txt in same folder)
#  - Resets/regenerates configs on first load if configured
# ============================================================
# ============================================================
#  AutoMod by Jazzzzz - Final v1.0 (patched) + Exempt list
# ============================================================

import hexchat
import os
import re
import time
import json
import random
import fnmatch

__module_name__ = "AutoMod by Jazzzzz"
__module_version__ = "1.0 Powered by Jazzzzz"
__module_description__ = "Auto kick/ban with wildcards, reliable QUOTE KICK, per-channel protection, exempt list"

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
EXEMPT_FILE = os.path.join(BASE_DIR, "exempt.txt")

# Random message files
NICK_MSG_FILE = os.path.join(BASE_DIR, "nick_kickmsgs.txt")
WORD_MSG_FILE = os.path.join(BASE_DIR, "word_kickmsgs.txt")
FLOOD_MSG_FILE = os.path.join(BASE_DIR, "flood_kickmsgs.txt")

# -------------------------
# Ensure message files exist
# -------------------------
def ensure_random_msg_files():
    files = [NICK_MSG_FILE, WORD_MSG_FILE, FLOOD_MSG_FILE]
    for fp in files:
        if not os.path.exists(fp):
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("# One message per line — randomly chosen each time.\n")
                    f.write("# Example lines:\n")
                    f.write("Watch your nick!\n")
                    f.write("Language not allowed!\n")
                    f.write("Calm down, spammer!\n")
                hexchat.prnt(f"[AutoMod] Created {os.path.basename(fp)}")
            except Exception as e:
                hexchat.prnt(f"[AutoMod] Error creating {fp}: {e}")
ensure_random_msg_files()

# -------------------------
# Defaults & timers
# -------------------------
UNBAN_CHECK_MS = 60 * 1000
KICK_DELAY_MS = 700

DEFAULTS = {
    "UNBAN_MINUTES": 60,
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
bad_nick_rules = {}   # pattern -> (compiled_re, message, minutes, is_wild)
bad_word_rules = {}
protected_channels = set()
flood_records = {}    # (chan_lower, nick_lower) -> [timestamps]
whitelist_nicks = set(["ChanServ", "NickServ"])
exempt_set = set()    # loaded from exempt.txt

# -------------------------
# Logging & persistence
# -------------------------
def timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def log(msg):
    try:
        # print to HexChat console (AutoMod tab)
        ctx = hexchat.find_context(server=None, channel="AutoMod")
        if not ctx:
            hexchat.command("QUERY AutoMod")
            ctx = hexchat.find_context(channel="AutoMod")
        ctx.prnt(f"[{timestamp()}] {msg}")
    except Exception:
        try:
            hexchat.prnt(f"[AutoMod] {msg}")
        except Exception:
            pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{timestamp()} - {msg}\n")
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
    files = [BAD_NICKS_FILE, BAD_WORDS_FILE, PROTECTED_FILE, EXEMPT_FILE, NICK_MSG_FILE, WORD_MSG_FILE, FLOOD_MSG_FILE]
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
                    elif fp == BAD_WORDS_FILE:
                        f.write("# bad_words.txt - pattern :: message :: minutes(optional)\n")
                    elif fp == PROTECTED_FILE:
                        f.write("# protected_channels.txt - one channel per line (lowercase)\n")
                    elif fp == EXEMPT_FILE:
                        f.write("# exempt.txt - one nick or mask per line (e.g. nick123 OR *!*@example.com)\n")
                    else:
                        f.write("# autogenerated\n")
            except Exception as e:
                log(f"Error creating {fp}: {e}")

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
                is_wildcard = "*" in pat
                cre, is_wild = pattern_to_regex(pat, is_new_rule=is_wildcard)
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

# -------------------------
# Load protected channels from file
# -------------------------
def load_protected_channels(reset=False):
    """Load protected channels from file into memory."""
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
                    # allow lines that start with '#' (channel names)
                    if s and not s.startswith("# "):  # skip commented lines only
                        protected_channels.add(s.lower())
            log(f"Loaded {len(protected_channels)} protected channels: {', '.join(protected_channels) or '<none>'}")
        except Exception as e:
            log(f"Error loading protected channels: {e}")
    else:
        log("No protected_channels.txt found — creating a new one.")
        save_protected_channels()


# -------------------------
# Save protected channels to file
# -------------------------
def save_protected_channels():
    """Save the protected channels list to PROTECTED_FILE."""
    try:
        with open(PROTECTED_FILE, "w", encoding="utf-8") as f:
            f.write("# protected_channels.txt - one channel per line (lowercase)\n")
            for channel in sorted(protected_channels):
                f.write(f"{channel}\n")
        log(f"Saved {len(protected_channels)} protected channels.")
    except Exception as e:
        log(f"Error saving protected channels: {e}")

# -------------------------
# Exempt list helpers
# -------------------------
def load_exempt_list():
    global exempt_set
    exempt_set = set()
    if os.path.exists(EXEMPT_FILE):
        try:
            with open(EXEMPT_FILE, "r", encoding="utf-8") as fh:
                for raw in fh:
                    s = raw.strip()
                    if s and not s.startswith("#"):
                        exempt_set.add(s)
            log(f"Loaded exempt list ({len(exempt_set)} entries).")
        except Exception as e:
            log(f"Error loading exempt list: {e}")
    else:
        # Create default file
        try:
            with open(EXEMPT_FILE, "w", encoding="utf-8") as fh:
                fh.write("# exempt.txt - one nick or mask per line (e.g. nick123 OR *!*@example.com)\n")
            log("Created exempt.txt")
        except Exception as e:
            log(f"Error creating exempt file: {e}")

def save_exempt_list():
    try:
        with open(EXEMPT_FILE, "w", encoding="utf-8") as fh:
            fh.write("# exempt.txt - one nick or mask per line\n")
            for e in sorted(exempt_set):
                fh.write(e + "\n")
        log(f"Saved exempt list ({len(exempt_set)} entries).")
    except Exception as e:
        log(f"Error saving exempt list: {e}")

def get_user_host(nick):
    """Return ident@host if found via userlist, else None"""
    try:
        users = hexchat.get_list("users")
        if not users:
            return None
        for u in users:
            if u.nick and u.nick.lower() == nick.lower():
                # u.host usually is "ident@hostname"
                return u.host  # may be None
    except Exception:
        pass
    return None

def is_exempt(nick):
    """
    Exempt logic (Option B):
    - if exempt entry contains '@' or '!' treat as a mask and match against 'nick!ident@host' or '*!*@host'
    - if entry looks like plain nick (no '*' and no '@'), compare lower-case equality
    - wildcard entries (with *) are matched with fnmatch against mask string (nick!ident@host) and also nick
    """
    if not exempt_set:
        return False

    # direct nick whitelist (exact)
    for e in exempt_set:
        if "@" not in e and "!" not in e and "*" not in e:
            if nick.lower() == e.lower():
                return True

    # try to get ident@host (user host)
    hostpart = get_user_host(nick)  # ident@host or None
    mask_to_test = None
    if hostpart:
        mask_to_test = f"{nick}!{hostpart}"
    else:
        # If host not found, still allow plain nick wildcard matching
        mask_to_test = nick

    for e in exempt_set:
        if not e:
            continue
        # Normalize
        entry = e.strip()
        # If entry contains wildcard, use fnmatch on mask_to_test and nick as fallback
        if "*" in entry:
            try:
                if mask_to_test and fnmatch.fnmatch(mask_to_test.lower(), entry.lower()):
                    return True
                if fnmatch.fnmatch(nick.lower(), entry.lower()):
                    return True
            except Exception:
                pass
            continue
        # If entry contains '@' or '!' treat as mask (match full mask)
        if "@" in entry or "!" in entry:
            if mask_to_test and fnmatch.fnmatch(mask_to_test.lower(), entry.lower()):
                return True
            # also try match host-only (like *!*@host)
            if hostpart and fnmatch.fnmatch(hostpart.lower(), entry.lower()):
                return True
            continue
        # plain nick already handled, but double-check (case-insensitive)
        if nick.lower() == entry.lower():
            return True

    return False

# -------------------------
# Load everything
# -------------------------
def load_all(reset=False):
    ensure_files_exist(reset)
    load_settings()
    global bad_nick_rules, bad_word_rules
    bad_nick_rules = load_rules_from_file(BAD_NICKS_FILE)
    bad_word_rules = load_rules_from_file(BAD_WORDS_FILE)
    load_protected_channels(reset)
    load_exempt_list()
    log(f"Loaded {len(bad_nick_rules)} nick rules, {len(bad_word_rules)} word rules, {len(protected_channels)} protected channels.")

load_all(reset=False)

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
# Ban & Kick (QUOTE) - ban uses host when available
# -------------------------
def ban_mask_for_nick(nick):
    host = get_user_host(nick)
    if host:
        # host is ident@hostname -> we want *!*@hostname (host ban)
        try:
            ident, hostname = host.split("@", 1)
            return f"*!*@{hostname}"
        except Exception:
            pass
    return f"{nick}!*@*"

def apply_ban_and_kick(channel, nick, reason, duration_minutes=None):
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
        log(f"Set ban {mask} in {channel} — reason: {reason}")
    except Exception as e:
        log(f"Error issuing ban: {e}")

    def do_kick():
        try:
            hexchat.command(cmd_kick_quote)
            log(f"Sent QUOTE KICK {channel} {nick} :{reason}")
        except Exception as e:
            log(f"Failed QUOTE KICK {nick} in {channel}: {e}")

    schedule_once(KICK_DELAY_MS, do_kick)

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
    try:
        if len(word) < 1:
            return hexchat.EAT_NONE

        nick = word[0]
        channel = hexchat.get_info("channel")

        if not is_protected(channel):
            return hexchat.EAT_NONE

        if is_whitelisted(nick):
            return hexchat.EAT_NONE

        # ✅ Check exemption (host-aware if your is_exempt supports host)
        if is_exempt(nick):
            return hexchat.EAT_NONE

        nick_l = nick.lower()

        for pat, (cre, msg, dur, is_wild) in bad_nick_rules.items():
            try:
                if not cre.search(nick):
                    continue

                if is_wild:
                    core = re.sub(r"\s+", "", pat)
                    core = re.sub(r"\*+", "*", core)
                    core = core.replace("*", "").strip().lower()
                    if core and core == nick_l:
                        log(f"Wildcard rule '{pat}' skipped for exact-match nick '{nick}'")
                        continue

                # ✅ show join BEFORE kicking
                hexchat.prnt(f"--> {nick} has joined {channel}")

                reason = msg or get_random_msg(
                    NICK_MSG_FILE,
                    settings.get("BANMSG", "") or "AutoMod: Prohibited nickname"
                )
                apply_ban_and_kick(
                    channel,
                    nick,
                    reason,
                    dur if dur is not None else settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"])
                )

                return hexchat.EAT_NONE      # ✅ allow JOIN to appear

            except Exception as e:
                log(f"Error checking join rule '{pat}' against nick '{nick}': {e}")
                continue

    except Exception as e:
        log(f"on_join exception: {e}")

    return hexchat.EAT_NONE


def on_message(word, word_eol, userdata):
    try:
        if len(word) < 2:
            return hexchat.EAT_NONE

        nick = word[0]
        message = word_eol[1] if len(word_eol) > 1 else word[1]
        channel = hexchat.get_info("channel")

        if not is_protected(channel):
            return hexchat.EAT_NONE

        if is_whitelisted(nick):
            return hexchat.EAT_NONE

        # ✅ Check exemption
        if is_exempt(nick):
            return hexchat.EAT_NONE

        # --- FLOOD DETECTION ---
        if record_message_for_flood(channel, nick):
            # ✅ show message BEFORE kick/ban
            hexchat.prnt(f"{nick}: {message}")

            reason = get_random_msg(
                FLOOD_MSG_FILE,
                settings.get("KICKMSG", "") or settings.get("BANMSG", "") or "Flooding the channel"
            )

            apply_ban_and_kick(
                channel,
                nick,
                reason,
                settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"])
            )

            flood_records.pop((channel.lower(), nick.lower()), None)

            return hexchat.EAT_NONE   # ✅ do NOT hide flood message

        # --- BAD WORD DETECTION ---
        for pat, (cre, msg, dur, is_wild) in bad_word_rules.items():
            try:
                if cre.search(message):

                    # ✅ show message BEFORE ban
                    hexchat.prnt(f"{nick}: {message}")

                    reason = msg or get_random_msg(
                        WORD_MSG_FILE,
                        settings.get("BANMSG", "") or "AutoMod: Prohibited language"
                    )

                    apply_ban_and_kick(
                        channel,
                        nick,
                        reason,
                        dur if dur is not None else settings.get("UNBAN_MINUTES", DEFAULTS["UNBAN_MINUTES"])
                    )

                    return hexchat.EAT_NONE   # ✅ do NOT hide message

            except Exception as e:
                log(f"Error checking word rule '{pat}' against message: {e}")
                continue

    except Exception as e:
        log(f"on_message exception: {e}")

    return hexchat.EAT_NONE


# -------------------------
# Random message helper
# -------------------------
def get_random_msg(filepath, default_msg=""):
    try:
        if not os.path.exists(filepath):
            return default_msg
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        if not lines:
            return default_msg
        return random.choice(lines)
    except Exception as e:
        log(f"Error reading random message from {filepath}: {e}")
        return default_msg

# -------------------------
# Commands
# -------------------------
def cmd_reload(word, word_eol, userdata):
    load_all(reset=False)
    log("Rules & settings reloaded.")
    return hexchat.EAT_ALL

def cmd_list(word, word_eol, userdata):
    hexchat.prnt("=== AutoMod Rules & Settings ===")
    hexchat.prnt(f"Protected channels: {', '.join(sorted(protected_channels)) or '<none>'}")
    hexchat.prnt(f"Settings: UNBAN_MINUTES={settings.get('UNBAN_MINUTES')}, FLOOD={settings.get('FLOOD_COUNT')} msgs/{settings.get('FLOOD_SECONDS')}s")
    hexchat.prnt("-- Bad Nicks --")
    for pat, (_, msg, dur, _) in bad_nick_rules.items():
        hexchat.prnt(f"{pat} :: {msg} :: {dur if dur is not None else settings.get('UNBAN_MINUTES')}m")
    hexchat.prnt("-- Bad Words --")
    for pat, (_, msg, dur, _) in bad_word_rules.items():
        hexchat.prnt(f"{pat} :: {msg} :: {dur if dur is not None else settings.get('UNBAN_MINUTES')}m")
    hexchat.prnt("-- Exempt List --")
    if exempt_set:
        for e in sorted(exempt_set):
            hexchat.prnt(f"{e}")
    else:
        hexchat.prnt("<none>")
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

# -------------------------
# Toggle protection for a channel
# -------------------------
def cmd_chan(word, word_eol, userdata):
    if len(word) < 2:
        hexchat.prnt("Usage: /AMCHAN <#channel>")
        return hexchat.EAT_ALL

    channel = word[1].strip().lower()

    # Ensure the channel starts with '#'
    if not channel.startswith("#"):
        hexchat.prnt("Channel must start with #")
        return hexchat.EAT_ALL

    # Toggle protection
    if channel in protected_channels:
        protected_channels.remove(channel)
        hexchat.prnt(f"Removed protection for {channel}")
    else:
        protected_channels.add(channel)
        hexchat.prnt(f"Added protection for {channel}")

    # Save protected channels immediately after modification
    save_protected_channels()

    return hexchat.EAT_ALL
# -------------------------
# Initialize the script
# -------------------------
# Define RESET_CONFIGS before using it
RESET_CONFIGS = False  # Change to True if you want to reset configurations

# Initialize function to load everything
def initialize():
    load_protected_channels()  # Ensure protected channels are loaded at startup
    # Other initialization code (e.g., load settings, rules, etc.)
    load_all(reset=RESET_CONFIGS)

# Call the initialization function to load everything
initialize()


# -------------------------
# Call the initialization function to load everything
# -------------------------
initialize()

# -------------------------
# Register the AMCHAN command
# -------------------------
hexchat.hook_command("AMCHAN", cmd_chan, help="/AMCHAN #channel — Toggle protection for a channel")

def cmd_unchan(word, word_eol, userdata):
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
        "/AMEXEMPT ADD <entry>   Add exempt nick or mask",
        "/AMEXEMPT DEL <entry>   Remove exempt entry",
        "/AMEXEMPT LIST          Show exempt list",
        "/AMSET UNBAN_MINUTES <n>   Set auto-unban minutes",
        "/AMSET KICKMSG <text>      Set default kick message",
        "/AMSET BANMSG <text>       Set default ban message",
        "/AMSET FLOOD <count> <s>   Configure flood detection",
        "/AUTORELOAD     Reload rules and settings",
    ]
    for l in help_lines:
        hexchat.prnt(l)
    return hexchat.EAT_ALL

# -------------------------
# Exempt command
# -------------------------
def cmd_am_exempt(word, word_eol, userdata):
    # Usage: /AMEXEMPT ADD <entry> | DEL <entry> | LIST
    if len(word) < 2:
        hexchat.prnt("Usage: /AMEXEMPT ADD <nick/host> | DEL <nick/host> | LIST")
        return hexchat.EAT_ALL
    action = word[1].upper()
    target = " ".join(word[2:]).strip() if len(word) >= 3 else None
    if action == "ADD":
        if not target:
            hexchat.prnt("Usage: /AMEXEMPT ADD <nick/host/mask>")
            return hexchat.EAT_ALL
        exempt_set.add(target)
        save_exempt_list()
        hexchat.prnt(f"✅ Added to exempt list: {target}")
        return hexchat.EAT_ALL
    if action == "DEL":
        if not target:
            hexchat.prnt("Usage: /AMEXEMPT DEL <nick/host/mask>")
            return hexchat.EAT_ALL
        if target in exempt_set:
            exempt_set.remove(target)
            save_exempt_list()
            hexchat.prnt(f"❌ Removed from exempt list: {target}")
        else:
            hexchat.prnt("Not found in exempt list.")
        return hexchat.EAT_ALL
    if action == "LIST":
        hexchat.prnt("📌 Exempt List:")
        if exempt_set:
            for e in sorted(exempt_set):
                hexchat.prnt(f"  - {e}")
        else:
            hexchat.prnt("  <none>")
        return hexchat.EAT_ALL
    hexchat.prnt("Usage: /AMEXEMPT ADD <nick/host> | DEL <nick/host> | LIST")
    return hexchat.EAT_ALL

# -------------------------
# Menu / small UI
# -------------------------
def show_text_menu(word=None, word_eol=None, userdata=None):
    lines = [
        "────────── AutoMod by Jazzzzz ──────────",
        "1) Add Bad Nick    -> /AMADD nick <pattern>::<message>::<minutes?>",
        "2) Add Bad Word    -> /AMADD word <pattern>::<message>::<minutes?>",
        "3) List Rules      -> /AMLIST",
        "4) Delete Rule     -> /AMDEL <nick|word> <pattern>",
        "5) Toggle Protect  -> /AMCHAN #channel",
        "6) Flood Settings  -> /AMSET FLOOD <count> <seconds>",
        "7) Exempt Control  -> /AMEXEMPT LIST  (Add: /AMEXEMPT ADD <entry>)",
        "8) Reload Rules    -> /AUTORELOAD",
        "9) Quick Help      -> /AMHELP",
        "───────────────────────────────────────",
    ]
    for l in lines:
        hexchat.prnt(l)
    return hexchat.EAT_ALL

# -------------------------
# Hooks & init
# -------------------------
hexchat.hook_print("Join", on_join)
hexchat.hook_print("Channel Message", on_message)

hexchat.hook_command("AUTORELOAD", cmd_reload)
hexchat.hook_command("AMLIST", cmd_list)
hexchat.hook_command("AMADD", cmd_add)
hexchat.hook_command("AMDEL", cmd_del)
hexchat.hook_command("AMCHAN", cmd_chan)
hexchat.hook_command("AMUNCHAN", cmd_unchan)
hexchat.hook_command("AMSET", cmd_set)
hexchat.hook_command("AMGUI", cmd_gui)
hexchat.hook_command("AMHELP", cmd_help)
hexchat.hook_command("AMMENU", show_text_menu)
hexchat.hook_command("AMEXEMPT", cmd_am_exempt)

show_text_menu()
if os.path.exists(README_PATH):
    log(f"Documentation: {README_PATH}")
else:
    log("README not found in addons folder.")
log(f"{__module_name__} v{__module_version__} loaded. Protected: {', '.join(sorted(protected_channels)) or '<none>'}")


# End of script
