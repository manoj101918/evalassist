import { createClient } from "@supabase/supabase-js";

// Used only for sign-in; all data goes through the FastAPI backend.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
);
