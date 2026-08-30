COMPLETE SERVICES FOLDER
========================

Files included:

database.py
    Supabase client connection.

ui.py
    Current NCAA Women's Volleyball sidebar/header styling and shared UI helpers.

dvsport_sync.py
    DV Sport Challenge + POI sync, Big Ten/MVC/MAC, adjustable date range,
    defaulting to the prior 7 days through today.

challenge_download.py
    Builds/downloads Challenge ZIP packages containing all usable angles
    plus Challenge_Info.txt.

challenge_email.py
    Email Challenge modal, saved recipients, selectable email content,
    Challenge ZIP preparation, and Gmail compose-link generation.

__init__.py
    Package marker.

IMPORTANT
---------
Keep your existing:
    assets/ncaa-wvblogo.png
    .streamlit/secrets.toml

The email service expects the Supabase email_recipients table if you want
saved/default recipients. Without it, manual email addresses still work.
