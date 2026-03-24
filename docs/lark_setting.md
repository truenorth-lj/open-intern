# Lark (Feishu) Bot Setup

This guide walks you through creating a Lark bot and connecting it to your Open Intern agent.

## 1. Create a Custom App

Go to [Lark Open Platform](https://open.larksuite.com/app) and click **Create Custom App**.

![create custom app](image/lark_setting/1774276754079.png)

## 2. Add Permission Scopes

Navigate to the **Permissions & Scopes** page.

![permissions page](image/lark_setting/1774276804507.png)

1. Click **Add permission scopes to app**.
2. Search for `im:message` and add the following scopes:
   - **Receive messages sent to the bot in peer-to-peer chats** (`im:message.p2p_msg` / `im:message.p2p_msg:readonly`)
   - **Receive group chat messages mentioning the bot** (`im:message.group_msg` / `im:message.group_msg:readonly`)
   - **Send messages as bot** (`im:message:send_as_bot`)
3. Click **Add Scopes** to confirm.

## 3. Get App ID and App Secret

Go to the **Credentials** page.

![credentials page](image/lark_setting/1774276979032.png)

Copy the **App ID** and **App Secret**.

![copy credentials](image/lark_setting/1774277051313.png)

## 4. Connect to Open Intern

Open the Open Intern dashboard, navigate to your agent's **Settings** page, and paste the App ID and App Secret in the Lark section.

![paste in dashboard](image/lark_setting/1774277083750.png)

Click **Create Agent** to finish setup. Your Lark bot is now connected.
