require("dotenv").config();
const express = require("express");
const cors = require("cors");
const stripe = require("stripe")(process.env.STRIPE_SECRET_KEY);
const { createClient } = require("@supabase/supabase-js");
const nodemailer = require("nodemailer");
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const app = express();

// ── Supabase ──────────────────────────────────────────────
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

// ── Email transporter (Gmail) ─────────────────────────────
let emailTransporter = null;
if (process.env.EMAIL_USER && process.env.EMAIL_PASS) {
  emailTransporter = nodemailer.createTransport({
    service: "gmail",
    auth: {
      user: process.env.EMAIL_USER,
      pass: process.env.EMAIL_PASS,
    },
  });
  console.log("Email configured:", process.env.EMAIL_USER);
} else {
  console.log("Email not configured — set EMAIL_USER and EMAIL_PASS to enable");
}

// ── CORS ──────────────────────────────────────────────────
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

const FORM_NAMES = {
  i90: "I-90 — Renew or Replace Green Card",
  i130: "I-130 — Petition for Alien Relative",
  n400: "N-400 — Application for U.S. Citizenship",
  i485: "I-485 — Apply for a Green Card",
  i765: "I-765 — Work Permit (EAD)",
  i821d: "I-821D — DACA Renewal",
  i751: "I-751 — Remove Conditions on Green Card",
  i131: "I-131 — Travel Document",
  i129f: "I-129F — Fiancé(e) Visa (K-1)",
};

// ── Temp directory for PDFs ───────────────────────────────
const TMP_DIR = path.join(__dirname, "tmp");
if (!fs.existsSync(TMP_DIR)) fs.mkdirSync(TMP_DIR, { recursive: true });

// ── Health check ──────────────────────────────────────────
app.get("/", async (req, res) => {
  const { count } = await supabase
    .from("sessions")
    .select("*", { count: "exact", head: true })
    .eq("payment_status", "paid");
  res.json({
    status: "ok",
    service: "USA Docs API",
    total_paid_sessions: count || 0,
    email_enabled: !!emailTransporter,
  });
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

    // Persist answers to Supabase
    const { error: dbError } = await supabase.from("sessions").insert({
      id: session.id,
      form_id: formId,
      form_number: formNumber || "",
      form_name: formName || "",
      answers,
      payment_status: "pending",
    });

    if (dbError) {
      console.error("Supabase insert error:", dbError.message);
      // Don't fail the checkout — answers can still work from Stripe metadata
    }

    console.log(`Checkout created: ${session.id} for ${formId}`);
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
      // Update Supabase with payment confirmation
      const customerEmail =
        session.customer_details?.email || session.customer_email;

      await supabase
        .from("sessions")
        .update({
          payment_status: "paid",
          customer_email: customerEmail,
          amount_paid: session.amount_total,
          paid_at: new Date().toISOString(),
        })
        .eq("id", req.params.sessionId);

      res.json({
        paid: true,
        formId: session.metadata.formId,
        formNumber: session.metadata.formNumber,
        customerEmail,
      });
    } else {
      res.json({ paid: false });
    }
  } catch (err) {
    console.error("Verify error:", err.message);
    res.status(500).json({ error: "Failed to verify payment" });
  }
});

// ── Helper: generate a PDF file ───────────────────────────
function generatePDF(formId, answers, type) {
  const uniqueId = crypto.randomBytes(4).toString("hex");
  const answersFile = path.join(TMP_DIR, `answers_${uniqueId}.json`);
  const outputFile = path.join(
    TMP_DIR,
    `${formId}_${type}_${uniqueId}.pdf`
  );

  fs.writeFileSync(answersFile, JSON.stringify(answers));

  try {
    if (type === "instructions") {
      execSync(
        `python3 pdf-engine/generate_instructions.py "${formId}" "${answersFile}" "${outputFile}"`,
        { cwd: __dirname, timeout: 60000 }
      );
    } else {
      execSync(
        `python3 pdf-engine/fill_form.py "${formId}" "${answersFile}" "${outputFile}"`,
        { cwd: __dirname, timeout: 120000 }
      );
    }
    try { fs.unlinkSync(answersFile); } catch (e) {}
    return outputFile;
  } catch (err) {
    try { fs.unlinkSync(answersFile); } catch (e) {}
    try { fs.unlinkSync(outputFile); } catch (e) {}
    throw err;
  }
}

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

    // Get answers from Supabase
    const { data: row, error: dbError } = await supabase
      .from("sessions")
      .select("answers")
      .eq("id", sessionId)
      .single();

    if (dbError || !row) {
      return res.status(404).json({
        error:
          "Session not found. Your answers may have expired. Please fill out the form again.",
      });
    }

    const answers = row.answers;

    try {
      const outputFile = generatePDF(formId, answers, type || "form");

      // Mark as generated in Supabase
      if (type !== "instructions") {
        await supabase
          .from("sessions")
          .update({ pdf_generated: true })
          .eq("id", sessionId);
      }

      const filename =
        type === "instructions"
          ? `${formId.toUpperCase()}_Filing_Instructions.pdf`
          : `${formId.toUpperCase()}_Completed.pdf`;

      res.setHeader("Content-Type", "application/pdf");
      res.setHeader(
        "Content-Disposition",
        `attachment; filename="${filename}"`
      );

      const stream = fs.createReadStream(outputFile);
      stream.pipe(res);
      stream.on("end", () => {
        try { fs.unlinkSync(outputFile); } catch (e) {}
      });
    } catch (pyErr) {
      console.error(
        "Python error:",
        pyErr.stderr?.toString() || pyErr.message
      );
      res
        .status(500)
        .json({ error: "Failed to generate PDF. Please try again." });
    }
  } catch (err) {
    console.error("Generate error:", err.message);
    res.status(500).json({ error: "Failed to generate document" });
  }
});

// ── 4. Email PDFs to customer ─────────────────────────────
app.post("/api/email-documents/:sessionId", async (req, res) => {
  try {
    const { sessionId } = req.params;

    if (!emailTransporter) {
      return res
        .status(503)
        .json({ error: "Email delivery is not configured." });
    }

    // Verify payment
    const session = await stripe.checkout.sessions.retrieve(sessionId);
    if (session.payment_status !== "paid") {
      return res.status(402).json({ error: "Payment required" });
    }

    const formId = session.metadata.formId;
    const customerEmail =
      session.customer_details?.email || session.customer_email;

    if (!customerEmail) {
      return res
        .status(400)
        .json({ error: "No email address found for this payment." });
    }

    // Get answers from Supabase
    const { data: row, error: dbError } = await supabase
      .from("sessions")
      .select("answers")
      .eq("id", sessionId)
      .single();

    if (dbError || !row) {
      return res.status(404).json({ error: "Session not found." });
    }

    // Generate both PDFs
    let formPdf, instructionsPdf;
    try {
      formPdf = generatePDF(formId, row.answers, "form");
      instructionsPdf = generatePDF(formId, row.answers, "instructions");
    } catch (pyErr) {
      console.error("PDF generation error:", pyErr.message);
      return res
        .status(500)
        .json({ error: "Failed to generate documents for email." });
    }

    const formName = FORM_NAMES[formId] || formId.toUpperCase();

    // Send email
    await emailTransporter.sendMail({
      from: `"USA Docs" <${process.env.EMAIL_USER}>`,
      to: customerEmail,
      subject: `Your ${formId.toUpperCase()} Documents Are Ready — USA Docs`,
      html: `
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 32px 24px;">
          <h1 style="color: #1a1a2e; font-size: 24px; margin-bottom: 8px;">Your Documents Are Ready</h1>
          <p style="color: #4a5568; font-size: 15px; line-height: 1.6; margin-bottom: 24px;">
            Thank you for using USA Docs. Your completed <strong>${formName}</strong> and filing instructions are attached to this email.
          </p>

          <div style="background: #f0f9ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 20px; margin-bottom: 24px;">
            <h3 style="color: #1e40af; font-size: 15px; margin: 0 0 8px 0;">Next Steps:</h3>
            <p style="color: #4a5568; font-size: 14px; line-height: 1.7; margin: 0;">
              1. Print your completed form<br>
              2. Sign where indicated<br>
              3. Gather the documents listed in your filing checklist<br>
              4. Mail everything to the USCIS address in your instructions<br>
              5. Include your USCIS filing fee (check or money order)
            </p>
          </div>

          <p style="color: #4a5568; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
            You can also re-download your documents anytime by visiting:<br>
            <a href="${process.env.FRONTEND_URL}/success?session_id=${sessionId}&form=${formId}" style="color: #2563eb;">${process.env.FRONTEND_URL}/success?session_id=${sessionId}&form=${formId}</a>
          </p>

          <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">

          <p style="color: #94a3b8; font-size: 11px; line-height: 1.6;">
            USA Docs is a document preparation service. We are not lawyers. We are not a government agency. We do not provide legal advice.
            If you need legal help, please consult an immigration attorney.
          </p>
          <p style="color: #94a3b8; font-size: 11px;">
            Questions? Contact us at <a href="mailto:usadocs777@gmail.com" style="color: #2563eb;">usadocs777@gmail.com</a>
          </p>
        </div>
      `,
      attachments: [
        {
          filename: `${formId.toUpperCase()}_Completed.pdf`,
          path: formPdf,
        },
        {
          filename: `${formId.toUpperCase()}_Filing_Instructions.pdf`,
          path: instructionsPdf,
        },
      ],
    });

    // Cleanup temp files
    try { fs.unlinkSync(formPdf); } catch (e) {}
    try { fs.unlinkSync(instructionsPdf); } catch (e) {}

    // Mark email sent in Supabase
    await supabase
      .from("sessions")
      .update({ email_sent: true })
      .eq("id", sessionId);

    console.log(`Email sent to ${customerEmail} for ${formId}`);
    res.json({ success: true, email: customerEmail });
  } catch (err) {
    console.error("Email error:", err.message);
    res.status(500).json({ error: "Failed to send email. Please try again." });
  }
});

// ── Start ─────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`USA Docs API running on port ${PORT}`);
});
