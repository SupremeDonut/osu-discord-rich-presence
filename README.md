# osu-discord-rich-presence
Discord rich presence for playing osu!

___
## Using this program
### Requirements
  - Python 3.10+
  - Dependencies (`pip install -r requirements.txt`)
  - [gosumemory](https://github.com/l3lackShark/gosumemory)
  
### Setup

- Download the source code or clone the repository
- Download [gosumemory](https://github.com/l3lackShark/gosumemory)
- Create an OAuth application for osu!
  - Go to your [settings](https://osu.ppy.sh/home/account/edit) on the osu! website and scroll to the bottom
  - Scroll to the bottom and click **"New OAuth Application"**
  - Set the name to anything and leave the url blank
  - After registering an application take note of the **Client ID** and **Client Secret**
- Rename `.env.example` to `.env` and fill in the necessary information
  - `PLAYER_ID` is your osu! player id
  - `CLIENT_ID` and `CLIENT_SECRET` is the id and secret from your OAuth application
  - `OSU_PATH` and `GOSUMEMORY_PATH` are the file locations for osu! and gosumemory respectively, and will run those programs if specified
  
### Running

After the setup is complete you can then run `main.py`.

Make sure both osu! and discord are open.

If you see nothing happens try turning off rich presence in any other apps you might have open (including osu!), or restart your pc

If you encounter a problem message `SupremeDonut#2332` on Discord.
