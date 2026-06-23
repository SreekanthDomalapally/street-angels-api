from app.models import GroupInvite, User


def phone_placeholder_email(e164: str) -> str:
    return f"{e164.replace('+', '')}@phone.pending"


def invite_matches_user(invite: GroupInvite, user: User) -> bool:
    if invite.status != "pending":
        return False
    if user.phone_number and invite.invitee_phone and invite.invitee_phone == user.phone_number:
        return True
    if user.email and invite.invitee_email.lower() == user.email.lower():
        if invite.invitee_email.endswith("@phone.pending"):
            return False
        return True
    if user.phone_number and invite.invitee_email == phone_placeholder_email(user.phone_number):
        return True
    return False
