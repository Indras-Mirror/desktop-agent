"""MPRIS D-Bus media player control — reliable alternative to clicking play buttons."""

import subprocess
import json


def _dbus_get(player, prop):
    """Get a property from an MPRIS player."""
    result = subprocess.run(
        ["dbus-send", "--print-reply", f"--dest=org.mpris.MediaPlayer2.{player}",
         "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.Get",
         "string:org.mpris.MediaPlayer2.Player", f"string:{prop}"],
        capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _dbus_method(player, method):
    """Call a method on an MPRIS player."""
    result = subprocess.run(
        ["dbus-send", "--print-reply", f"--dest=org.mpris.MediaPlayer2.{player}",
         "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _dbus_open_uri(player, uri):
    """Open a URI in an MPRIS player."""
    result = subprocess.run(
        ["dbus-send", "--print-reply", f"--dest=org.mpris.MediaPlayer2.{player}",
         "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.OpenUri",
         f"string:{uri}"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def list_players():
    """List available MPRIS media players."""
    result = subprocess.run(
        ["dbus-send", "--print-reply", "--dest=org.freedesktop.DBus",
         "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
        capture_output=True, text=True
    )
    players = []
    if result.returncode == 0:
        for line in result.stdout.split("\n"):
            if "org.mpris.MediaPlayer2." in line:
                name = line.strip().strip('"').replace("org.mpris.MediaPlayer2.", "")
                players.append(name)
    return players


def _find_player(name=None):
    """Find a player by name, or return the first available."""
    players = list_players()
    if not players:
        print("✗ No media players found via D-Bus")
        return None
    if name:
        name_lower = name.lower()
        for p in players:
            if name_lower in p.lower():
                return p
        print(f"✗ Player '{name}' not found. Available: {', '.join(players)}")
        return None
    return players[0]


def _parse_metadata(raw):
    """Extract useful fields from MPRIS metadata output."""
    info = {}
    lines = raw.split("\n")
    for i, line in enumerate(lines):
        if "xesam:title" in line and i + 1 < len(lines):
            info["title"] = lines[i + 1].strip().strip('"').replace("variant", "").strip().strip('"')
        elif "xesam:artist" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip().strip('"')
                if val and val not in ("variant", "array [", "]", "string"):
                    info["artist"] = val
                    break
        elif "xesam:album" in line and i + 1 < len(lines):
            info["album"] = lines[i + 1].strip().strip('"').replace("variant", "").strip().strip('"')
    return info


def media_command(action, player_name=None, uri=None):
    """Execute a media control action."""
    player = _find_player(player_name)
    if not player:
        return False

    if action == "play":
        if _dbus_method(player, "Play"):
            print(f"✓ {player}: Playing")
            return True
    elif action == "pause":
        if _dbus_method(player, "Pause"):
            print(f"✓ {player}: Paused")
            return True
    elif action == "toggle":
        if _dbus_method(player, "PlayPause"):
            print(f"✓ {player}: Toggled play/pause")
            return True
    elif action == "next":
        if _dbus_method(player, "Next"):
            print(f"✓ {player}: Next track")
            return True
    elif action == "prev":
        if _dbus_method(player, "Previous"):
            print(f"✓ {player}: Previous track")
            return True
    elif action == "stop":
        if _dbus_method(player, "Stop"):
            print(f"✓ {player}: Stopped")
            return True
    elif action == "status":
        status_raw = _dbus_get(player, "PlaybackStatus")
        meta_raw = _dbus_get(player, "Metadata")
        status = "Unknown"
        if status_raw:
            for line in status_raw.split("\n"):
                line = line.strip().strip('"')
                if line in ("Playing", "Paused", "Stopped"):
                    status = line
                    break
        info = _parse_metadata(meta_raw) if meta_raw else {}
        print(f"✓ {player}: {status}")
        if info.get("title"):
            print(f"  Track: {info['title']}")
        if info.get("artist"):
            print(f"  Artist: {info['artist']}")
        if info.get("album"):
            print(f"  Album: {info['album']}")
        return True
    elif action == "open" and uri:
        if _dbus_open_uri(player, uri):
            print(f"✓ {player}: Opening {uri}")
            return True
    elif action == "players":
        players = list_players()
        if players:
            print(f"Available players: {', '.join(players)}")
        else:
            print("No media players found")
        return True
    else:
        print(f"✗ Unknown media action: {action}")
        print("  Actions: play, pause, toggle, next, prev, stop, status, players, open")
        return False

    print(f"✗ {action} failed for {player}")
    return False
