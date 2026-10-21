"""Best-effort transactional LINE notice; never changes membership or retries grants."""
import account_access
import line_ui
import membership


def status_text(status):
    if status == 'sent':
        return '開通通知已送出（不代表已讀）。'
    return '權限已生效，但通知未確認送出，請另行告知會員；勿重複開通。'


def send_grant(g, uid, expiry, renewed=False):
    # uid comes exclusively from the verified account binding, never a client recipient.
    if not g.CHANNEL_ACCESS_TOKEN:
        return 'unconfirmed'
    try:
        username = account_access.profile(uid)['username'] or '尚未綁定帳號'
        title = '續期成功' if renewed else '開通成功'
        text = (f'會員中心｜{title}\n\n帳號：{username}\n'
                f'到期：{expiry.astimezone(membership.TZ_TW).strftime("%Y-%m-%d %H:%M")}（台灣時間）\n'
                '會員權限已生效，可以開始使用。')
        response = g.line_session().post(
            'https://api.line.me/v2/bot/message/push',
            headers={'Authorization': f'Bearer {g.CHANNEL_ACCESS_TOKEN}',
                     'Content-Type': 'application/json'},
            json={'to': uid, 'messages': line_ui.build_messages(
                text, [('開始使用', '主選單'), ('會員中心', '會員中心')])},
            timeout=(3, 8),
        )
        # LINE acceptance is not proof of delivery (e.g. the recipient blocked the OA).
        return 'sent' if response.status_code == 200 else 'unconfirmed'
    except Exception as exc:
        # Do not log request bodies, recipient identities, or authorization headers.
        g.app.logger.warning('MEMBER_NOTICE unconfirmed error_type=%s', type(exc).__name__)
        return 'unconfirmed'
