require("dotenv").config();
const express = require("express");
const cors = require("cors");
const stripe = require("stripe")(process.env.STRIPE_SECRET_KEY);
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const app = express();

// CORS — allow frontend
const allowedOrigins = (process.env.FRONTEND_URL || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
app.use(
  cors({
    origin: (origin, cb) => {
      if (!origin || allowedOrigins.length === 0 || allowedOrigins.includes(origin))
        return cb(null, true);
      cb(null, false);
    },
  })
);
app.use(express.json({ limit: "2mb" }));

// ── Stripe Price Map ──────────────────────────────────────
const PRICE_MAP = {
  i90: process.env.PRICE_I90,
  i765: process.env.PRICE_I765,
  i131: process.env.PRICE_I131,
  i821d: process.env.PRICE_I821D,
  i130: process.env.PRICE_I130,
  i751: process.env.PRICE_I751,
  i129f: process.env.PRICE_I129F,
  n400: process.env.PRICE_N400,
  i485: process.env.PRICE_I485,
};

// ── In-memory answer store ────────────────────────────────
// Keys: Stripe session ID → { formId, answers, createdAt }
// Entries auto-expire after 2 hours
const answerStore = new Map();

function cleanExpiredAnswers() {
  const twoHoursAgo = Date.now() - 2 * 60 * 60 * 1000;
  for (const [key, val] of answerStore) {
    if (val.createdAt < twoHoursAgo) answerStore.delete(key);
  }
}
setInterval(cleanExpiredAnswers, 10 * 60 * 1000);

// ── Temp directory for PDFs ───────────────────────────────
const TMP_DIR = path.join(__dirname, "tmp");
if (!fs.existsSync(TMP_DIR)) fs.mkdirSync(TMP_DIR, { recursive: true });

// ── Health check ──────────────────────────────────────────
app.get("/", (req, res) => {
  res.json({ status: "ok", service: "USA Docs API", answers_stored: answerStore.size });
});

// ── 1. Store answers + create Stripe Checkout ─────────────
app.post("/api/checkout", async (req, res) => {
  try {
    const { formId, formNumber, formName, customerEmail, answers } = req.body;

    const priceId = PRICE_MAP[formId];
    if (!priceId) {
      return res.status(400).json({ error: "Invalid form selection" });
    }
    if (!answers || typeof answers !== "object") {
      return res.status(400).json({ error: "Answers are required" });
    }

    const sessionParams = {
      payment_method_types: ["card"],
      mode: "payment",
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${process.env.FRONTEND_URL}/success?session_id={CHECKOUT_SESSION_ID}&form=${formId}`,
      cancel_url: `${process.env.FRONTEND_URL}/?canceled=true&form=${formId}`,
      metadata: {
        formId,
        formNumber: formNumber || "",
        formName: formName || "",
      },
    };

    if (customerEmail) {
      sessionParams.customer_email = customerEmail;
    }

    const session = await stripe.checkout.sessions.create(sessionParams);

    // Store answers keyed by session ID
    answerStore.set(session.id, {
      formId,
      answers,
      createdAt: Date.now(),
    });

    console.log(`Checkout created: ${session.id} for ${formId} (${Object.keys(answers).length} answers stored)`);
    res.json({ url: session.url, sessionId: session.id });
  } catch (err) {
    console.error("Checkout error:", err.message);
    res.status(500).json({ error: "Failed to create checkout session" });
  }
});

// ── 2. Verify payment ────────────────────────────────────
app.get("/api/verify-payment/:sessionId", async (req, res) => {
  try {
    const session = await stripe.checkout.sessions.retrieve(req.params.sessionId);

    if (session.payment_status === "paid") {
      res.json({
        paid: true,
        formId: session.metadata.formId,
        formNumber: session.metadata.formNumber,
        customerEmail: session.customer_details?.email || session.customer_email,
        hasAnswers: answerStore.has(req.params.sessionId),
      });
    } else {
      res.json({ paid: false });
    }
  } catch (err) {
    console.error("Verify error:", err.message);
    res.status(500).json({ error: "Failed to verify payment" });
  }
});

// ── 3. Generate filled PDF (payment-gated) ────────────────
app.get("/api/generate-pdf/:sessionId", async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { type } = req.query; // "form" or "instructions"

    // Verify payment first
    const session = await stripe.checkout.sessions.retrieve(sessionId);
    if (session.payment_status !== "paid") {
      return res.status(402).json({ error: "Payment required" });
    }

    const formId = session.metadata.formId;

    // Get stored answers
    const stored = answerStore.get(sessionId);
    if (!stored) {
      return res.status(404).json({
        error: "Answers not found. They may have expired. Please fill out the form again.",
      });
    }

    const answers = stored.answers;
    const uniqueId = crypto.randomBytes(4).toString("hex");
    const answersFile = path.join(TMP_DIR, `answers_${uniqueId}.json`);
    const outputFile = path.join(TMP_DIR, `${formId}_${type || "form"}_${uniqueId}.pdf`);

    // Write answers to temp file for Python
    fs.writeFileSync(answersFile, JSON.stringify(answers));

    try {
      if (type === "instructions") {
        execSync(
          `python3 pdf-engine/generate_instructions.py "${formId}" "${answersFile}" "${outputFile}"`,
          { cwd: __dirname, timeout: 60000 }
        );
        console.log(`Instructions generated: ${formId}`);
      } else {
        execSync(
          `python3 pdf-engine/fill_form.py "${formId}" "${answersFile}" "${outputFile}"`,
          { cwd: __dirname, timeout: 120000 }
        );
        console.log(`Form filled: ${formId}`);
      }

      // Stream the PDF back
      const filename =
        type === "instructions"
          ? `${formId.toUpperCase()}_Filing_Instructions.pdf`
          : `${formId.toUpperCase()}_Completed.pdf`;

      res.setHeader("Content-Type", "application/pdf");
      res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);

      const stream = fs.createReadStream(outputFile);
      stream.pipe(res);
      stream.on("end", () => {
        try { fs.unlinkSync(answersFile); } catch (e) {}
        try { fs.unlinkSync(outputFile); } catch (e) {}
      });
    } catch (pyErr) {
      console.error("Python error:", pyErr.stderr?.toString() || pyErr.message);
      try { fs.unlinkSync(answersFile); } catch (e) {}
      try { fs.unlinkSync(outputFile); } catch (e) {}
      res.status(500).json({ error: "Failed to generate PDF. Please try again." });
    }
  } catch (err) {
    console.error("Generate error:", err.message);
    res.status(500).json({ error: "Failed to generate document" });
  }
});

// ── Start ─────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`USA Docs API running on port ${PORT}`);
});
