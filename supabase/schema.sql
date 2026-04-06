-- USA Docs - Supabase Schema
-- Run this in your Supabase SQL Editor

-- Sessions table: stores customer answers keyed by Stripe session ID
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,                    -- Stripe checkout session ID
  form_id TEXT NOT NULL,                  -- e.g. "i90", "n400"
  form_number TEXT,                       -- e.g. "I-90", "N-400"
  form_name TEXT,                         -- e.g. "Renew or Replace Green Card"
  answers JSONB NOT NULL,                 -- customer's interview answers
  customer_email TEXT,                    -- email from Stripe after payment
  payment_status TEXT DEFAULT 'pending',  -- pending, paid, failed
  amount_paid INTEGER,                    -- cents
  pdf_generated BOOLEAN DEFAULT FALSE,    -- has the customer downloaded their form?
  email_sent BOOLEAN DEFAULT FALSE,       -- have we emailed the PDFs?
  created_at TIMESTAMPTZ DEFAULT NOW(),
  paid_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for looking up by payment status
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(payment_status);

-- Index for cleanup of old unpaid sessions
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sessions_updated_at
  BEFORE UPDATE ON sessions
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- RLS: disable for now since only the backend (service role) accesses this
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role full access" ON sessions
  FOR ALL
  USING (true)
  WITH CHECK (true);
