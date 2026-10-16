"""User-invoked Microsoft Graph subscription setup and maintenance.

Subscriptions require a publicly reachable HTTPS, route-limited reverse proxy.
This script never opens that proxy and never grants Entra permissions.
"""
import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import httpx
from app.core.config import settings
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import is_public_https_callback

BASE = 'https://graph.microsoft.com/v1.0'


def safe_https(url: str) -> str:
    if not is_public_https_callback(url):
        raise ValueError('Callback must be a public HTTPS address without local/private destinations, URL credentials or fragments.')
    return url


async def run(args):
    if not all((settings.graph_client_state, settings.graph_tenant_id, settings.graph_client_id,
                settings.graph_client_secret, settings.graph_mailbox)):
        raise SystemExit('Configure GRAPH_CLIENT_STATE, tenant, client ID/secret, and mailbox first.')
    headers = {'Authorization': f'Bearer {await application_token()}', 'Content-Type': 'application/json'}
    async with httpx.AsyncClient(timeout=25) as client:
        if args.create:
            notification = safe_https(args.create)
            if not notification.endswith('/api/v1/automation/graph/notifications'):
                raise ValueError('Notification URL must end with the exact dedicated route.')
            lifecycle = notification.replace('/graph/notifications', '/graph/lifecycle')
            payload = {
                'changeType': 'created',
                'notificationUrl': notification,
                'lifecycleNotificationUrl': lifecycle,
                'resource': f"users/{settings.graph_mailbox}/mailFolders('Inbox')/messages",
                'expirationDateTime': (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                'clientState': settings.graph_client_state,
            }
            response = await client.post(BASE + '/subscriptions', headers=headers, json=payload)
        elif args.renew:
            response = await client.patch(BASE + '/subscriptions/' + args.renew, headers=headers,
                json={'expirationDateTime': (datetime.now(UTC) + timedelta(days=2)).isoformat()})
        else:
            response = await client.get(BASE + '/subscriptions/' + args.status, headers=headers)
        if response.status_code not in {200, 201, 204}:
            raise SystemExit(f'Graph HTTP {response.status_code}: check permissions and callback reachability. Do not print secrets.')
        data = response.json() if response.content else {}
        print('Subscription ID:', data.get('id', args.renew or args.status))
        print('Expiration:', data.get('expirationDateTime', 'Updated; check with --status.'))
        if args.create:
            print('Save the new ID privately in GRAPH_SUBSCRIPTION_ID, recreate API/worker, and renew before expiration.')


def main():
    parser = argparse.ArgumentParser(description='Create, renew or check a basic Outlook-message subscription.')
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--create', metavar='PUBLIC_HTTPS_NOTIFICATION_URL')
    options.add_argument('--renew', metavar='SUBSCRIPTION_ID')
    options.add_argument('--status', metavar='SUBSCRIPTION_ID')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
