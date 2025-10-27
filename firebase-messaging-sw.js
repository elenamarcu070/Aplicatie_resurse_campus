// Fișier service worker — permite primirea notificărilor chiar și cu browserul închis
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCSpEw7T1FZL-SF7L6UP3LKptDvtjoMtOw",
  projectId: "washtuiasi-push",
  messagingSenderId: "452249356230",
  appId: "1:452249356230:web:21ebdc556b3bd56abed4c7"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log("📩 [Service Worker] Message received:", payload);
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: "/static/images/logo.png"
  };
  self.registration.showNotification(notificationTitle, notificationOptions);
});
