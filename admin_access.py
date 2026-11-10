"""Fail-closed access gate for the legacy advanced/admin panel.

Set ADMIN_PASSWORD in Streamlit Secrets. Optionally set ADMIN_EMAILS and use
Streamlit's configured OIDC login (st.user). Neither mechanism grants GitHub access.
"""
import hmac


def _secret(secrets, key):
    try:
        value = secrets.get(key, '')
    except (KeyError, AttributeError, FileNotFoundError):
        return ''
    return value.strip() if isinstance(value, str) else ''


def email_allowed(email, allowlist):
    if not email or not allowlist:
        return False
    allowed = {x.strip().casefold() for x in allowlist.split(',') if x.strip()}
    return email.strip().casefold() in allowed


def authorized(st):
    """Render authorization UI; return True only for verified administrator."""
    allowed_emails = _secret(st.secrets, 'ADMIN_EMAILS')
    if allowed_emails:
        user = getattr(st, 'user', None)
        try:
            logged_in = bool(user.is_logged_in)
            email = user.get('email', '') if logged_in else ''
        except (AttributeError, TypeError, KeyError):
            logged_in, email = False, ''
        if logged_in and email_allowed(email, allowed_emails):
            return True
        st.warning('관리자 전용 메뉴입니다. 허용된 관리자 계정으로 로그인해야 합니다.')
        return False

    password = _secret(st.secrets, 'ADMIN_PASSWORD')
    if not password:
        st.info('관리자 메뉴는 잠겨 있습니다. 운영자가 Streamlit Secrets에 ADMIN_PASSWORD 또는 ADMIN_EMAILS를 설정해야 합니다.')
        return False
    if st.session_state.get('_admin_authenticated') is True:
        if st.button('관리자 로그아웃', key='_admin_logout'):
            st.session_state['_admin_authenticated'] = False
            st.rerun()
        return True
    attempts = int(st.session_state.get('_admin_failed_attempts', 0))
    if attempts >= 5:
        st.error('인증 시도 횟수를 초과했습니다. 새 세션에서 다시 시도하세요.')
        return False
    with st.form('_admin_login_form'):
        entered = st.text_input('관리자 비밀번호', type='password')
        submitted = st.form_submit_button('관리자 인증')
    if submitted:
        if hmac.compare_digest(entered.encode('utf-8'), password.encode('utf-8')):
            st.session_state['_admin_authenticated'] = True
            st.session_state['_admin_failed_attempts'] = 0
            st.rerun()
        else:
            st.session_state['_admin_failed_attempts'] = attempts + 1
            st.error('관리자 비밀번호가 올바르지 않습니다.')
    return False
