const functions = require("firebase-functions");
const admin = require("firebase-admin");
const axios = require("axios");
const cors = require("cors")({ origin: true });
const bcrypt = require("bcryptjs");

admin.initializeApp();
const db = admin.firestore();

/* ======================
   🔐 SET PIN
====================== */
exports.setPin = functions.https.onRequest((req, res) => {
  cors(req, res, async () => {
    const { uid, pin } = req.body;

    try {
      const hash = await bcrypt.hash(pin, 10);

      await db.doc(`users/${uid}`).update({
        pinHash: hash
      });

      res.send({ success: true });
    } catch (err) {
      res.status(500).send(err.message);
    }
  });
});

/* ======================
   💸 WITHDRAW
====================== */
exports.withdraw = functions.https.onRequest((req, res) => {
  cors(req, res, async () => {
    const { uid, amount, pin } = req.body;

    try {
      const userRef = db.doc(`users/${uid}`);
      const snap = await userRef.get();

      if (!snap.exists) return res.status(404).send("User not found");

      const user = snap.data();

      const match = await bcrypt.compare(pin, user.pinHash || "");

      if (!match) return res.status(400).send("Invalid PIN");

      if (user.balance < amount) {
        return res.status(400).send("Insufficient balance");
      }

      await userRef.update({
        balance: admin.firestore.FieldValue.increment(-amount)
      });

      await db.collection("withdrawals").add({
        userId: uid,
        amount,
        status: "pending",
        createdAt: admin.firestore.FieldValue.serverTimestamp()
      });

      res.send({ success: true });

    } catch (err) {
      res.status(500).send(err.message);
    }
  });
});

/* ======================
   💰 PAYSTACK VERIFY
====================== */
exports.verifyPayment = functions.https.onRequest((req, res) => {
  cors(req, res, async () => {

    const PAYSTACK_SECRET = "sk_test_xxxxx"; // replace later

    try {
      const { reference, uid, amount } = req.body;

      const verify = await axios.get(
        `https://api.paystack.co/transaction/verify/${reference}`,
        {
          headers: {
            Authorization: `Bearer ${PAYSTACK_SECRET}`
          }
        }
      );

      if (verify.data.data.status !== "success") {
        return res.status(400).send("Payment not verified");
      }

      await db.doc(`users/${uid}`).update({
        balance: admin.firestore.FieldValue.increment(amount)
      });

      res.send({ success: true });

    } catch (err) {
      res.status(500).send(err.message);
    }
  });
});

/* ======================
   🎁 REFERRAL BONUS
====================== */
exports.handleReferral = functions.auth.user().onCreate(async (user) => {
  const refCode = user?.customClaims?.ref || null;

  if (!refCode) return;

  const refSnap = await db.collection("referrals").doc(refCode).get();
  if (!refSnap.exists) return;

  const referrerId = refSnap.data().uid;

  const bonus = 200;

  await db.doc(`users/${referrerId}`).update({
    balance: admin.firestore.FieldValue.increment(bonus),
    referralBonus: admin.firestore.FieldValue.increment(bonus),
    referrals: admin.firestore.FieldValue.increment(1)
  });
});

/* ======================
   📈 DAILY EARNINGS
====================== */
exports.dailyEarnings = functions.pubsub.schedule("every 24 hours").onRun(async () => {
  const snap = await db.collection("investments")
    .where("status", "==", "approved")
    .get();

  const batch = db.batch();

  snap.forEach(docSnap => {
    const inv = docSnap.data();

    if (!inv.lastPaid) {
      inv.lastPaid = inv.createdAt;
    }

    const now = Date.now();
    const last = inv.lastPaid.toMillis();

    if (now - last >= 86400000) {
      const daily = (inv.amount * inv.roiPercent) / 100 / inv.duration;

      batch.update(docSnap.ref, {
        lastPaid: admin.firestore.Timestamp.now()
      });

      batch.update(db.doc(`users/${inv.userId}`), {
        balance: admin.firestore.FieldValue.increment(daily),
        totalEarnings: admin.firestore.FieldValue.increment(daily)
      });
    }
  });

  await batch.commit();
});
