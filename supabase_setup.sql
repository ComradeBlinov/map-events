create table if not exists events (
  id bigserial primary key,
  channel text not null,
  post_id bigint not null,
  ts timestamptz not null,
  text text not null,
  kind text not null,
  lat double precision,
  lon double precision,
  place text,
  confidence real not null,
  unique(channel, post_id)
);
create index if not exists events_ts_idx on events(ts desc);
alter table events enable row level security;
drop policy if exists "public read" on events;
create policy "public read" on events for select using (true);