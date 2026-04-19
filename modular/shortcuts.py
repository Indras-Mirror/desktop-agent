"""Common application keyboard shortcuts"""

SPOTIFY_SHORTCUTS = {
    "play": "space",
    "pause": "space",
    "next": "ctrl+Right",
    "previous": "ctrl+Left",
    "volume_up": "ctrl+Up",
    "volume_down": "ctrl+Down",
    "search": "ctrl+l",
    "like": "ctrl+s",
    "shuffle": "ctrl+s",
}

FIREFOX_SHORTCUTS = {
    "new_tab": "ctrl+t",
    "close_tab": "ctrl+w",
    "search": "ctrl+k",
    "url_bar": "ctrl+l",
    "reload": "ctrl+r",
    "bookmark": "ctrl+d",
}

CHROME_SHORTCUTS = {
    "new_tab": "ctrl+t",
    "close_tab": "ctrl+w",
    "search": "ctrl+k",
    "url_bar": "ctrl+l",
    "reload": "ctrl+r",
    "bookmark": "ctrl+d",
}

APP_SHORTCUTS = {
    "spotify": SPOTIFY_SHORTCUTS,
    "firefox": FIREFOX_SHORTCUTS,
    "chrome": CHROME_SHORTCUTS,
    "chromium": CHROME_SHORTCUTS,
}


def get_shortcut(app_name, action):
    """Get keyboard shortcut for app action"""
    app_lower = app_name.lower()
    for app, shortcuts in APP_SHORTCUTS.items():
        if app in app_lower:
            return shortcuts.get(action)
    return None


def list_shortcuts(app_name):
    """List all shortcuts for an app"""
    app_lower = app_name.lower()
    for app, shortcuts in APP_SHORTCUTS.items():
        if app in app_lower:
            return shortcuts
    return {}
