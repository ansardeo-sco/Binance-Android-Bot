from datetime import datetime, timezone

from models import Notification, BotEvent


class NotificationManager:

    @staticmethod
    def create(
        db,
        title,
        message,
        notification_type="INFO",
        symbol=None,
        cycle_id=None,
        severity="INFO",
    ):
        notification = Notification(
            cycle_id=cycle_id,
            symbol=symbol,
            title=title,
            message=message,
            notification_type=notification_type,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )

        event = BotEvent(
            event_type=notification_type,
            severity=severity,
            symbol=symbol,
            cycle_id=cycle_id,
            message=message,
            created_at=datetime.now(timezone.utc),
        )

        db.add(notification)
        db.add(event)

        return notification

    @staticmethod
    def mark_as_read(db, notification_id):
        notification = (
            db.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
        )

        if not notification:
            return False

        notification.is_read = True
        db.commit()

        return True


notification_manager = NotificationManager()
