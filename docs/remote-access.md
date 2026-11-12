# Let Mitchell use this Mac from his computer

You stay on your Mac and keep using it. This lets Mitchell open a terminal on your Mac, go to the kit folder, and run Codex or Claude Code there. He does not take over your mouse or your screen.

You need two things: Tailscale, so his computer can see yours, and Remote Login, so he can type commands. Mitchell sends you an invite link. You do not need to make up an account or a password for him.

## 1. Install Tailscale

1. Open Safari and go to [https://tailscale.com/download/mac](https://tailscale.com/download/mac).
2. Download the Mac app and open the file.
3. If it asks you to drag Tailscale into Applications, do that.
4. Open Tailscale from Applications.
5. If the Mac says it cannot be opened, go to **System Settings > Privacy & Security** and click **Open Anyway**.

Leave Tailscale running. Its icon sits in the menu bar at the top of the screen.

## 2. Join Mitchell's network

Mitchell sends you an invite link. It is a tailscale.com link. Use only the link he sends you. Do not forward it to anyone else.

1. Click the link.
2. Approve the prompts to join his network.
3. If Tailscale asks you to sign in, use the button on that invite. You do not need a separate account of your own unless Mitchell says so.

When it is connected, the Tailscale menu-bar icon shows that you are in. If you never got a link, ask Mitchell to send one. Do not hunt for a network name.

## 3. Turn on Remote Login

1. Open **System Settings**.
2. Go to **General**, then **Sharing**.
3. Turn on **Remote Login**.
4. If it asks who can connect, leave your own user on (the account you use on this Mac).

Your Mac should stay awake and plugged in while Mitchell is working. If it sleeps, the connection drops. You can keep using Mail, Safari, and everything else.

If his connection is refused, check **System Settings > Network > Firewall**. Remote Login should be allowed. Turning the firewall off is not required.

## 4. What Mitchell does

He opens Terminal on his computer and connects to your Mac over Tailscale. Then he opens the kit folder (`~/ColdApproach/matthew-studio-kit`) and runs Codex or Claude Code there. You keep using the Mac. Do not quit Tailscale, and do not turn Remote Login off, while he is in the middle of something.

This is a terminal on your Mac. It is not someone else driving the pointer.

## 5. Turn it off

When Mitchell says he is done, or any time you want to stop:

1. Open **System Settings > General > Sharing** and turn **Remote Login** off.
2. Click the Tailscale icon in the menu bar and disconnect, or quit Tailscale.

That stops him from connecting. Turning it back on later is the same two switches: Tailscale connected, then Remote Login on. Ask Mitchell for a fresh invite if the old link no longer works.
