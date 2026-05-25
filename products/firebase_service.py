from firebase_admin import messaging
# Ensure this import matches your actual project structure
from agriAuthentication.models import FCMToken 

def send_order_status_notification(user, order, status_display):
    # 1. Safely extract the token model using the same pattern as your chat consumer
    fcm_device = FCMToken.objects.filter(user=user).first()
    
    print(f"\n--- DEBUG FCM ---")
    
    # 2. Check if the device token exists
    if not fcm_device:
        print("❌ ERROR: The buyer does not have an FCM token saved in the database! Notification aborted.")
        return

    print(f"✅ Buyer Token Found: {fcm_device.token}")

    # 3. Build the message using fcm_device.token
    message = messaging.Message(
        notification=messaging.Notification(
            title=f"Order Update: {order.tracking_number}",
            body=f"Your order status has been updated to: {status_display}"
        ),
        data={
            "type": "order_status_update",
            "order_id": str(order.id)
        },
        token=fcm_device.token, # 👈 Extracted exactly like your chat consumer
    )
    
    try:
        messaging.send(message)
        print(f"✅ Order status FCM successfully sent for order {order.id}")    
    except Exception as e:
        print(f"❌ FCM Error: {e}")