# Troubleshooting

The app writes a log to `~/Library/Application Support/PS5 Cheater/ps5-cheater.log`.

## macOS says the app cannot be opened

The app is not signed. Open **System Settings > Privacy & Security**, scroll down and click **Open Anyway**.

## Network blocked

macOS is stopping the app from reaching local devices.

1. Open **System Settings > Privacy & Security > Local Network**.
2. Turn on **PS5 Cheater**.
3. Wait a few seconds. If the badge does not change, quit and reopen the app.

If that is on already, check that the Mac and the PS5 are on the same network and that no VPN is blocking local traffic.

## Console not found

- Make sure the PS5 is on, and Remote Play is enabled.
- Some routers isolate Wi-Fi clients from each other. Try a guest-free network or a cable.
- Enter the IP address by hand on the **Connect** page.

## Another Remote Play session

The PS5 allows one session at a time and needs a few seconds to release the last one. The app retries for up to 40 seconds. Also close the official Remote Play app and any other device streaming from the console.

## Run finished but no cheat appeared

- The game must be in normal gameplay. In a menu, the presses go to the menu.
- A paused game ignores cheats. The game pauses each time the app disconnects, so unpause before the next run.
- Do not touch the controller during a run.
- Raise **Hold** and **Gap** under **Timing**.
- The code itself may be wrong. Only cheats marked **Tested on console** have been seen working.

## The game opens its menu after a run

That is the disconnect pausing the game. Unpause it yourself.

## Remove the app and its data

1. Press **Quit app** and delete **PS5 Cheater** from Applications.
2. Delete `~/Library/Application Support/PS5 Cheater` for the database and log.
3. Delete `~/.pyremoteplay` for the pairing data.
4. On the PS5, remove the device under **Settings > System > Remote Play > Link Device**.
