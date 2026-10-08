-- Empty isolated test database baseline, captured 2026-10-07; NOT a production restore.
-- Apply ONLY to a NEW EMPTY recovery database. Do not execute over existing tables.
BEGIN;
CREATE SEQUENCE "analysis_logs_id_seq" AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE TABLE "analysis_logs" (
  "id" integer DEFAULT nextval('analysis_logs_id_seq'::regclass) NOT NULL,
  "line_user_id" text NOT NULL,
  "predicted" text,
  "actual" text,
  "hit" boolean,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "analysis_logs_pkey" PRIMARY KEY (id)
);
CREATE TABLE "users" (
  "line_user_id" text NOT NULL,
  "bound_account" text,
  "vip_expire_at" timestamp without time zone,
  "trial_started_at" timestamp without time zone,
  "trial_end_at" timestamp without time zone,
  "trial_expired_notice_sent" boolean DEFAULT false NOT NULL,
  "current_road" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "high_count" integer DEFAULT 0 NOT NULL,
  "low_count" integer DEFAULT 0 NOT NULL,
  "tie_count" integer DEFAULT 0 NOT NULL,
  "banker_pair_count" integer DEFAULT 0 NOT NULL,
  "player_pair_count" integer DEFAULT 0 NOT NULL,
  "pending_flow" text,
  "pending_main_result" text,
  "imported_ready" boolean DEFAULT false NOT NULL,
  "analysis_active" boolean DEFAULT false NOT NULL,
  "point_range" text,
  "play_mode" text,
  "target_profit" text,
  "last_prediction" text,
  "last_treasure_round" integer DEFAULT '-99'::integer NOT NULL,
  "round_win" integer DEFAULT 0 NOT NULL,
  "round_loss" integer DEFAULT 0 NOT NULL,
  "win_streak" integer DEFAULT 0 NOT NULL,
  "loss_streak" integer DEFAULT 0 NOT NULL,
  "max_win_streak" integer DEFAULT 0 NOT NULL,
  "max_loss_streak" integer DEFAULT 0 NOT NULL,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "users_pkey" PRIMARY KEY (line_user_id)
);
ALTER SEQUENCE "analysis_logs_id_seq" OWNED BY "analysis_logs"."id";
COMMIT;

