"""Database CRUD operations for Communications Hub, Threads, Templates, Accounts, and Browser Sessions."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

from app.communications.models import (
    Communication,
    CommunicationThread,
    MessageTemplate,
    EmailAccount,
    BrowserSession,
)


# --- Thread & Communication Logging Services ---

def create_thread(
    db: Session,
    candidate_id: Optional[int] = None,
    subject: Optional[str] = None,
    channel: str = "email",
    status: str = "active",
) -> Optional[CommunicationThread]:
    """Create a new communication thread.

    Args:
        db (Session): The database session.
        candidate_id (Optional[int]): ID of the candidate associated with the thread.
        subject (Optional[str]): Subject of the communication thread.
        channel (str): The channel of communication (e.g., 'email').
        status (str): Current status of the thread.

    Returns:
        Optional[CommunicationThread]: The created thread, or None if an error occurred.
    """
    try:
        thread = CommunicationThread(
            candidate_id=candidate_id,
            subject=subject,
            channel=channel,
            status=status,
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        return thread
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating thread: {e}", exc_info=True)
        return None


def get_thread(db: Session, thread_id: int) -> Optional[CommunicationThread]:
    """Retrieve a thread with its full list of messages.

    Args:
        db (Session): The database session.
        thread_id (int): ID of the thread to retrieve.

    Returns:
        Optional[CommunicationThread]: The requested thread, or None if not found or an error occurred.
    """
    try:
        stmt = (
            select(CommunicationThread)
            .options(joinedload(CommunicationThread.communications))
            .where(CommunicationThread.id == thread_id)
        )
        return db.scalars(stmt).unique().first()
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving thread {thread_id}: {e}", exc_info=True)
        return None


def list_threads(
    db: Session,
    candidate_id: Optional[int] = None,
    channel: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[CommunicationThread]:
    """List communication threads with optional filtering.

    Args:
        db (Session): The database session.
        candidate_id (Optional[int]): Filter by candidate ID.
        channel (Optional[str]): Filter by communication channel.
        limit (int): Maximum number of results to return.
        offset (int): Number of results to skip.

    Returns:
        List[CommunicationThread]: A list of threads matching the criteria.
    """
    try:
        stmt = select(CommunicationThread).options(joinedload(CommunicationThread.communications))
        if candidate_id is not None:
            stmt = stmt.where(CommunicationThread.candidate_id == candidate_id)
        if channel and channel.lower() != "all":
            stmt = stmt.where(CommunicationThread.channel == channel)
        stmt = stmt.order_by(CommunicationThread.updated_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).unique().all())
    except SQLAlchemyError as e:
        logger.error(f"Error listing threads: {e}", exc_info=True)
        return []


def log_communication(
    db: Session,
    thread_id: Optional[int] = None,
    candidate_id: Optional[int] = None,
    channel: str = "email",
    direction: str = "outbound",
    sender: str = "recruiter@talenthunt.os",
    recipient: str = "",
    body: str = "",
    subject: Optional[str] = None,
    status: str = "sent",
    metadata_json: Optional[str] = None,
) -> Optional[Communication]:
    """Log an incoming or outgoing communication message across channels.

    Args:
        db (Session): The database session.
        thread_id (Optional[int]): ID of the thread.
        candidate_id (Optional[int]): ID of the candidate.
        channel (str): The communication channel.
        direction (str): Direction of the communication (e.g., 'outbound').
        sender (str): Sender information.
        recipient (str): Recipient information.
        body (str): Body content of the communication.
        subject (Optional[str]): Subject of the communication.
        status (str): Status of the communication (e.g., 'sent').
        metadata_json (Optional[str]): Additional metadata in JSON format.

    Returns:
        Optional[Communication]: The logged communication, or None if an error occurred.
    """
    try:
        if not thread_id and candidate_id:
            # Create thread automatically if missing
            thread = CommunicationThread(
                candidate_id=candidate_id,
                subject=subject or f"{channel.title()} Thread",
                channel=channel,
                status="active"
            )
            db.add(thread)
            db.flush()
            thread_id = thread.id

        comm = Communication(
            thread_id=thread_id,
            candidate_id=candidate_id,
            channel=channel,
            direction=direction,
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            status=status,
            sent_at=datetime.now(timezone.utc) if status in ["sent", "received"] else None,
            metadata_json=metadata_json,
        )
        db.add(comm)

        # Touch thread updated_at timestamp
        if thread_id:
            db.execute(
                update(CommunicationThread)
                .where(CommunicationThread.id == thread_id)
                .values(updated_at=datetime.now(timezone.utc))
            )

        db.commit()
        db.refresh(comm)
        return comm
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error logging communication: {e}", exc_info=True)
        return None


def get_communication(db: Session, comm_id: int) -> Optional[Communication]:
    """Retrieve a single communication by ID.

    Args:
        db (Session): The database session.
        comm_id (int): ID of the communication to retrieve.

    Returns:
        Optional[Communication]: The retrieved communication, or None if not found or an error occurred.
    """
    try:
        return db.get(Communication, comm_id)
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving communication {comm_id}: {e}", exc_info=True)
        return None


def list_communications(
    db: Session,
    candidate_id: Optional[int] = None,
    thread_id: Optional[int] = None,
    channel: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Communication]:
    """List communication logs ordered by creation time descending.

    Args:
        db (Session): The database session.
        candidate_id (Optional[int]): Filter by candidate ID.
        thread_id (Optional[int]): Filter by thread ID.
        channel (Optional[str]): Filter by communication channel.
        limit (int): Maximum number of results to return.
        offset (int): Number of results to skip.

    Returns:
        List[Communication]: A list of communications matching the criteria.
    """
    try:
        stmt = select(Communication)
        if candidate_id is not None:
            stmt = stmt.where(Communication.candidate_id == candidate_id)
        if thread_id is not None:
            stmt = stmt.where(Communication.thread_id == thread_id)
        if channel and channel.lower() != "all":
            stmt = stmt.where(Communication.channel == channel)

        stmt = stmt.order_by(Communication.created_at.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all())
    except SQLAlchemyError as e:
        logger.error(f"Error listing communications: {e}", exc_info=True)
        return []


def update_communication_status(db: Session, comm_id: int, status: str) -> Optional[Communication]:
    """Update delivery/read status of a logged communication.

    Args:
        db (Session): The database session.
        comm_id (int): ID of the communication to update.
        status (str): The new status to set.

    Returns:
        Optional[Communication]: The updated communication, or None if not found or an error occurred.
    """
    try:
        comm = db.get(Communication, comm_id)
        if comm:
            comm.status = status
            if status == "read" and not comm.read_at:
                comm.read_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(comm)
        return comm
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating status for communication {comm_id}: {e}", exc_info=True)
        return None


# --- Message Template Services ---

def create_template(
    db: Session,
    name: str,
    body_template: str,
    channel: str = "email",
    category: str = "Outreach",
    subject: Optional[str] = None,
    variables_json: Optional[str] = None,
) -> Optional[MessageTemplate]:
    """Create a new outreach message template.

    Args:
        db (Session): The database session.
        name (str): Name of the template.
        body_template (str): The body template content.
        channel (str): The communication channel (default: 'email').
        category (str): Template category.
        subject (Optional[str]): Subject for the template.
        variables_json (Optional[str]): JSON string of variables used in the template.

    Returns:
        Optional[MessageTemplate]: The created template, or None if an error occurred.
    """
    try:
        tmpl = MessageTemplate(
            name=name,
            channel=channel,
            category=category,
            subject=subject,
            body_template=body_template,
            variables_json=variables_json or json.dumps(["candidate_name", "job_title", "company", "recruiter_name"]),
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)
        return tmpl
    except (SQLAlchemyError, TypeError, ValueError) as e:
        db.rollback()
        logger.error(f"Error creating template: {e}", exc_info=True)
        return None


def list_templates(db: Session, channel: Optional[str] = None) -> List[MessageTemplate]:
    """List message templates.

    Args:
        db (Session): The database session.
        channel (Optional[str]): Filter templates by channel.

    Returns:
        List[MessageTemplate]: A list of message templates.
    """
    try:
        stmt = select(MessageTemplate).where(MessageTemplate.is_active == True)
        if channel and channel.lower() != "all":
            stmt = stmt.where(MessageTemplate.channel == channel)
        stmt = stmt.order_by(MessageTemplate.category, MessageTemplate.name)
        return list(db.scalars(stmt).all())
    except SQLAlchemyError as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        return []


def get_template(db: Session, template_id: int) -> Optional[MessageTemplate]:
    """Retrieve template by ID.

    Args:
        db (Session): The database session.
        template_id (int): ID of the template.

    Returns:
        Optional[MessageTemplate]: The retrieved template, or None if not found or an error occurred.
    """
    try:
        return db.get(MessageTemplate, template_id)
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving template {template_id}: {e}", exc_info=True)
        return None


def update_template(db: Session, template_id: int, **kwargs: Any) -> Optional[MessageTemplate]:
    """Update template fields.

    Args:
        db (Session): The database session.
        template_id (int): ID of the template to update.
        **kwargs: Arbitrary keyword arguments containing fields to update.

    Returns:
        Optional[MessageTemplate]: The updated template, or None if not found or an error occurred.
    """
    try:
        tmpl = db.get(MessageTemplate, template_id)
        if tmpl:
            for key, val in kwargs.items():
                if hasattr(tmpl, key):
                    setattr(tmpl, key, val)
            tmpl.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(tmpl)
        return tmpl
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating template {template_id}: {e}", exc_info=True)
        return None


def delete_template(db: Session, template_id: int) -> bool:
    """Soft-delete or purge template.

    Args:
        db (Session): The database session.
        template_id (int): ID of the template to delete.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    try:
        tmpl = db.get(MessageTemplate, template_id)
        if tmpl:
            db.delete(tmpl)
            db.commit()
            return True
        return False
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting template {template_id}: {e}", exc_info=True)
        return False


def seed_default_templates_if_empty(db: Session) -> None:
    """Seed ready-to-use recruiting outreach templates if none exist."""
    existing_count = db.scalar(select(MessageTemplate.id).limit(1))
    if existing_count is not None:
        return

    defaults = [
        {
            "name": "Initial Engineering Outreach (Email)",
            "channel": "email",
            "category": "Initial Contact",
            "subject": "Opportunity: {{job_title}} role at {{company}}",
            "body_template": (
                "Hi {{candidate_name}},\n\n"
                "I came across your profile and was thoroughly impressed by your background in {{skills}}. "
                "We are currently searching for an exceptional {{job_title}} to lead key technical initiatives at {{company}}.\n\n"
                "Based in {{location}}, this role offers competitive compensation and high technical ownership.\n\n"
                "Would you be open for a brief 10-minute chat this week?\n\n"
                "Best regards,\n"
                "{{recruiter_name}}\n"
                "Talent Acquisition"
            ),
        },
        {
            "name": "LinkedIn InMail Quick Connection",
            "channel": "linkedin",
            "category": "Initial Contact",
            "subject": "Connecting re: {{job_title}} role",
            "body_template": (
                "Hi {{candidate_name}}, noticed your impressive track record as {{current_title}} at {{current_company}}. "
                "We have a high-impact {{job_title}} opening that fits your expertise in {{skills}}. "
                "Let's connect if you're open to exploring new opportunities!"
            ),
        },
        {
            "name": "Naukri Direct Recruiter Message",
            "channel": "naukri",
            "category": "Initial Contact",
            "subject": "Job Opportunity: {{job_title}}",
            "body_template": (
                "Dear {{candidate_name}},\n\n"
                "Greetings from {{company}}!\n"
                "Your profile matched our requirements for {{job_title}}. "
                "Required skills: {{skills}}.\n"
                "Please let us know your availability for a exploratory discussion.\n\n"
                "Regards,\n{{recruiter_name}}"
            ),
        },
        {
            "name": "Follow-Up (3 Days)",
            "channel": "email",
            "category": "Follow-up",
            "subject": "Re: Opportunity: {{job_title}} role at {{company}}",
            "body_template": (
                "Hi {{candidate_name}},\n\n"
                "Following up on my previous note regarding the {{job_title}} opportunity. "
                "I know you are busy, but I wanted to make sure my email didn't get buried.\n\n"
                "Let me know if you have 5 minutes for a quick conversation.\n\n"
                "Best,\n{{recruiter_name}}"
            ),
        },
    ]

    for d in defaults:
        create_template(
            db,
            name=d["name"],
            channel=d["channel"],
            category=d["category"],
            subject=d["subject"],
            body_template=d["body_template"],
        )


# --- Email Account Services ---

def create_email_account(
    db: Session,
    email_address: str,
    display_name: Optional[str] = None,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_username: Optional[str] = None,
    smtp_password: Optional[str] = None,
    is_default: bool = False,
) -> Optional[EmailAccount]:
    """Register an email account for outreach.

    Args:
        db (Session): The database session.
        email_address (str): The email address to register.
        display_name (Optional[str]): Display name for the account.
        smtp_host (str): SMTP server hostname.
        smtp_port (int): SMTP server port.
        smtp_username (Optional[str]): SMTP authentication username.
        smtp_password (Optional[str]): SMTP authentication password.
        is_default (bool): Whether this should be the default email account.

    Returns:
        Optional[EmailAccount]: The registered email account, or None if an error occurred.
    """
    try:
        if is_default:
            # Reset previous default
            db.execute(update(EmailAccount).values(is_default=False))

        acc = EmailAccount(
            email_address=email_address,
            display_name=display_name or email_address.split("@")[0].title(),
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username or email_address,
            smtp_password=smtp_password,
            is_default=is_default,
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)
        return acc
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating email account: {e}", exc_info=True)
        return None


def list_email_accounts(db: Session) -> List[EmailAccount]:
    """List configured email accounts.

    Args:
        db (Session): The database session.

    Returns:
        List[EmailAccount]: A list of email accounts ordered by default status.
    """
    try:
        return list(db.scalars(select(EmailAccount).order_by(EmailAccount.is_default.desc())).all())
    except SQLAlchemyError as e:
        logger.error(f"Error listing email accounts: {e}", exc_info=True)
        return []


def get_default_email_account(db: Session) -> Optional[EmailAccount]:
    """Get the primary default email account or first available.

    Args:
        db (Session): The database session.

    Returns:
        Optional[EmailAccount]: The default email account, or None if not found or an error occurred.
    """
    try:
        acc = db.scalar(select(EmailAccount).where(EmailAccount.is_default == True).limit(1))
        if not acc:
            acc = db.scalar(select(EmailAccount).limit(1))
        return acc
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving default email account: {e}", exc_info=True)
        return None


# --- Browser Session Services ---

def create_browser_session(
    db: Session,
    platform: str,
    session_name: str,
    target_url: Optional[str] = None,
) -> Optional[BrowserSession]:
    """Record an active browser session.

    Args:
        db (Session): The database session.
        platform (str): The platform name (e.g., 'linkedin').
        session_name (str): The name of the browser session.
        target_url (Optional[str]): The URL of the session.

    Returns:
        Optional[BrowserSession]: The created browser session, or None if an error occurred.
    """
    try:
        sess = BrowserSession(
            platform=platform.lower(),
            session_name=session_name,
            target_url=target_url or f"https://www.{platform.lower()}.com",
            last_accessed_at=datetime.now(timezone.utc),
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating browser session: {e}", exc_info=True)
        return None


def list_browser_sessions(db: Session, platform: Optional[str] = None) -> List[BrowserSession]:
    """List saved browser sessions.

    Args:
        db (Session): The database session.
        platform (Optional[str]): Filter sessions by platform.

    Returns:
        List[BrowserSession]: A list of saved browser sessions.
    """
    try:
        stmt = select(BrowserSession)
        if platform and platform.lower() != "all":
            stmt = stmt.where(BrowserSession.platform == platform.lower())
        return list(db.scalars(stmt.order_by(BrowserSession.created_at.desc())).all())
    except SQLAlchemyError as e:
        logger.error(f"Error listing browser sessions: {e}", exc_info=True)
        return []


def get_browser_session(db: Session, session_id: int) -> Optional[BrowserSession]:
    """Retrieve browser session by ID.

    Args:
        db (Session): The database session.
        session_id (int): ID of the session to retrieve.

    Returns:
        Optional[BrowserSession]: The retrieved browser session, or None if not found or an error occurred.
    """
    try:
        return db.get(BrowserSession, session_id)
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving browser session {session_id}: {e}", exc_info=True)
        return None
