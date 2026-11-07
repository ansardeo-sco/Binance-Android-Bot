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

        now = datetime.now(timezone.utc)

        notification = Notification(
            cycle_id=cycle_id,
            symbol=symbol,
            title=str(title),
            message=str(message),
            notification_type=str(notification_type),
            is_read=False,
            created_at=now,
        )

        event = BotEvent(
            event_type=str(notification_type),
            severity=str(severity),
            symbol=symbol,
            cycle_id=cycle_id,
            message=str(message),
            created_at=now,
        )

        db.add(notification)
        db.add(event)

        return notification

    @staticmethod
    def mark_as_read(db, notification_id):

        notification = (
            db.query(Notification)
            .filter(
                Notification.id == notification_id
            )
            .first()
        )

        if not notification:
            return False

        if notification.is_read:
            return True

        notification.is_read = True
        db.commit()

        return True

    @staticmethod
    def mark_all_as_read(db):

        notifications = (
            db.query(Notification)
            .filter(Notification.is_read.is_(False))
            .all()
        )

        for notification in notifications:
            notification.is_read = True

        db.commit()

        return {
            "success": True,
            "updated": len(notifications),
        }


notification_manager = NotificationManager()
