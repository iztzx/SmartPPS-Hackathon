-- 1. Reset (Just in case)
drop table if exists public.profiles cascade;

-- 2. Create the User Profile Table with App-Specific Fields
create table public.profiles (
  id uuid references auth.users not null primary key,
  
  -- QR Passport Fields (From the form in Tab 3)
  head_name text, 
  ic_number text, 
  home_address text,
  family_size integer,
  
  -- Situation Report / Vulnerabilities (Decoded from Tab 1)
  -- The app stores an array of strings like ['Warga Emas/Bedridden', 'Pet/Cat']
  vulnerabilities jsonb default '[]'::jsonb, 
  
  -- The final generated JKM payload (raw QR text)
  jkm_payload text,
  
  -- Tracking Location (Taken from userLocation JS object)
  last_known_location_city text,
  last_known_location_lat double precision,
  last_known_location_lon double precision,
  
  updated_at timestamp with time zone default timezone('utc'::text, now())
);

-- 3. Security (Row Level Security) - Policies are already correct
alter table public.profiles enable row level security;

create policy "Users can view own profile" 
  on public.profiles for select using (auth.uid() = id);

create policy "Users can update own profile" 
  on public.profiles for update using (auth.uid() = id);

create policy "Users can insert own profile" 
  on public.profiles for insert with check (auth.uid() = id);

-- 4. Enable Realtime 
alter publication supabase_realtime add table public.profiles;

-- Optional: Create a function/trigger to update 'updated_at' automatically
CREATE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_profile_updated_at BEFORE UPDATE
ON profiles FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
