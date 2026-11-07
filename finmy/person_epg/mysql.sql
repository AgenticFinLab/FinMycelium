-- Person EPG 3.0. Fresh schema only; existing databases require a separate migration.
-- MySQL 8.0.17+; InnoDB; generated from schema_model.json.
-- Apply to an empty, already-selected schema. No DROP statements.
-- Foreign keys are added after table creation to permit declared reference cycles.

-- One native SubjectGraph; graph-local IDs are preserved verbatim.
CREATE TABLE `subject_graph` (
  `graph_id` VARCHAR(128) NOT NULL,
  `schema_version` VARCHAR(32) NOT NULL,
  `subject_entity_id` VARCHAR(128) NULL,
  `subject_type` VARCHAR(32) NOT NULL,
  `title` TEXT NOT NULL,
  `coverage_start` VARCHAR(32) NULL,
  `coverage_end` VARCHAR(32) NULL,
  `descriptions` JSON NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  PRIMARY KEY (`graph_id`),
  CONSTRAINT ck_person_subject CHECK (subject_type = 'individual')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- An entity identity within one graph, with descriptive scalar attributes.
CREATE TABLE `entity` (
  `graph_id` VARCHAR(128) NOT NULL,
  `entity_id` VARCHAR(128) NOT NULL,
  `name` TEXT NOT NULL,
  `entity_type` VARCHAR(64) NOT NULL,
  `attributes` JSON NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `entity_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Aliases are rows, not relationship arrays.
CREATE TABLE `entity_alias` (
  `graph_id` VARCHAR(128) NOT NULL,
  `entity_id` VARCHAR(128) NOT NULL,
  `alias` VARCHAR(255) NOT NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `entity_id`, `alias`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Independent occurrence; start/end reference temporal values, not renderer coordinates.
CREATE TABLE `occurrence` (
  `graph_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `title` TEXT NOT NULL,
  `subject_relevance` TEXT NOT NULL,
  `start_time_id` VARCHAR(128) NULL,
  `end_time_id` VARCHAR(128) NULL,
  `descriptions` JSON NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `occurrence_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Membership only: permits actions/transactions to reference actual participants without selecting a role record.
CREATE TABLE `occurrence_participant` (
  `graph_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `entity_id` VARCHAR(128) NOT NULL,
  PRIMARY KEY (`graph_id`, `occurrence_id`, `entity_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Role and temporal details of an occurrence participant; multiple role records remain valid.
CREATE TABLE `participation` (
  `graph_id` VARCHAR(128) NOT NULL,
  `participation_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `entity_id` VARCHAR(128) NOT NULL,
  `role` TEXT NOT NULL,
  `start_time_id` VARCHAR(128) NULL,
  `end_time_id` VARCHAR(128) NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `participation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Native actor_id and occurrence_id refer to occurrence membership; no role-interval inference.
CREATE TABLE `action` (
  `graph_id` VARCHAR(128) NOT NULL,
  `action_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `actor_id` VARCHAR(128) NOT NULL,
  `action_type` TEXT NOT NULL,
  `timestamp_time_id` VARCHAR(128) NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `action_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Transaction occurrence and optional known entity parties; unknown parties are NULL.
CREATE TABLE `financial_transaction` (
  `graph_id` VARCHAR(128) NOT NULL,
  `transaction_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `name` TEXT NOT NULL,
  `from_entity_id` VARCHAR(128) NULL,
  `to_entity_id` VARCHAR(128) NULL,
  `timestamp_time_id` VARCHAR(128) NULL,
  `details` JSON NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `transaction_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Ordered native instrument descriptions; no invented global instrument identity.
CREATE TABLE `transaction_instrument` (
  `graph_id` VARCHAR(128) NOT NULL,
  `transaction_id` VARCHAR(128) NOT NULL,
  `ordinal` INT UNSIGNED NOT NULL,
  `description` TEXT NOT NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  PRIMARY KEY (`graph_id`, `transaction_id`, `ordinal`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Time-qualified entity relationship independent of joint participation in any occurrence.
CREATE TABLE `entity_relation` (
  `graph_id` VARCHAR(128) NOT NULL,
  `relation_id` VARCHAR(128) NOT NULL,
  `from_entity_id` VARCHAR(128) NOT NULL,
  `to_entity_id` VARCHAR(128) NOT NULL,
  `relation_type` TEXT NOT NULL,
  `valid_from_time_id` VARCHAR(128) NULL,
  `valid_to_time_id` VARCHAR(128) NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `relation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Contextual M:N relation/occurrence association, without a co-participation requirement.
CREATE TABLE `relation_occurrence` (
  `graph_id` VARCHAR(128) NOT NULL,
  `relation_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `relation_id`, `occurrence_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Exact source text when available; no source is fabricated for unresolved quotations.
CREATE TABLE `source_document` (
  `graph_id` VARCHAR(128) NOT NULL,
  `document_id` VARCHAR(128) NOT NULL,
  `title` TEXT NULL,
  `source_url` TEXT NULL,
  `published_at` DATETIME(6) NULL,
  `content` LONGTEXT NOT NULL,
  PRIMARY KEY (`graph_id`, `document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Verbatim quote; document and half-open Unicode offsets are jointly known or jointly unknown.
CREATE TABLE `evidence_span` (
  `graph_id` VARCHAR(128) NOT NULL,
  `span_id` VARCHAR(128) NOT NULL,
  `document_id` VARCHAR(128) NULL,
  `char_start` BIGINT UNSIGNED NULL,
  `char_end` BIGINT UNSIGNED NULL,
  `quote` LONGTEXT NOT NULL,
  PRIMARY KEY (`graph_id`, `span_id`),
  CONSTRAINT `ck_span_location` CHECK ((`document_id` IS NULL AND `char_start` IS NULL AND `char_end` IS NULL) OR (`document_id` IS NOT NULL AND `char_start` IS NOT NULL AND `char_end` IS NOT NULL AND `char_end` > `char_start`)),
  CONSTRAINT `uq_resolved_span` UNIQUE (`graph_id`, `document_id`, `char_start`, `char_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Metadata contains reasons, confidence and evidence_status by local field path; no copied values or quotes.
CREATE TABLE `evidence_set` (
  `graph_id` VARCHAR(128) NOT NULL,
  `evidence_set_id` VARCHAR(128) NOT NULL,
  `field_metadata` JSON NULL,
  PRIMARY KEY (`graph_id`, `evidence_set_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- M:N field-to-quote references; actual FKs anchor every evidence container and span.
CREATE TABLE `evidence_link` (
  `graph_id` VARCHAR(128) NOT NULL,
  `evidence_set_id` VARCHAR(128) NOT NULL,
  `field_path` VARCHAR(255) NOT NULL,
  `quote_order` INT UNSIGNED NOT NULL,
  `span_id` VARCHAR(128) NOT NULL,
  PRIMARY KEY (`graph_id`, `evidence_set_id`, `field_path`, `quote_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Native value plus an optional explicitly supplied time_window; no inferred date bounds are cached.
CREATE TABLE `time_value` (
  `graph_id` VARCHAR(128) NOT NULL,
  `time_id` VARCHAR(128) NOT NULL,
  `value` VARCHAR(128) NOT NULL,
  `window_start` DATE NULL,
  `window_end` DATE NULL,
  `original_text` TEXT NULL,
  `is_approximate` BOOLEAN NULL,
  `window_semantics` VARCHAR(16) NULL,
  PRIMARY KEY (`graph_id`, `time_id`),
  CONSTRAINT `ck_time_window` CHECK ((`window_start` IS NULL AND `window_end` IS NULL AND `original_text` IS NULL AND `is_approximate` IS NULL) OR (`window_start` IS NOT NULL AND `window_end` IS NOT NULL AND `original_text` IS NOT NULL AND `is_approximate` IS NOT NULL AND `window_start` <= `window_end` AND `is_approximate` IN (0,1))),
  CONSTRAINT ck_window_semantics CHECK (window_semantics IS NULL OR (window_start IS NOT NULL AND window_semantics IN ('uncertainty','duration')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Optional graph-wide shorter label for an existing occurrence; original title is preserved.
CREATE TABLE `occurrence_label` (
  `graph_id` VARCHAR(128) NOT NULL,
  `occurrence_id` VARCHAR(128) NOT NULL,
  `label` TEXT NOT NULL,
  PRIMARY KEY (`graph_id`, `occurrence_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- One activity handle per existing action, transaction or contextual occurrence. No copied fact values.
CREATE TABLE `activity` (
  `graph_id` VARCHAR(128) NOT NULL,
  `activity_id` VARCHAR(128) NOT NULL,
  `action_id` VARCHAR(128) NULL,
  `transaction_id` VARCHAR(128) NULL,
  `context_occurrence_id` VARCHAR(128) NULL,
  PRIMARY KEY (`graph_id`, `activity_id`),
  CONSTRAINT ck_activity_one_fact CHECK ((CASE WHEN action_id IS NULL THEN 0 ELSE 1 END + CASE WHEN transaction_id IS NULL THEN 0 ELSE 1 END + CASE WHEN context_occurrence_id IS NULL THEN 0 ELSE 1 END) = 1),
  CONSTRAINT uq_activity_action UNIQUE (graph_id, action_id),
  CONSTRAINT uq_activity_transaction UNIQUE (graph_id, transaction_id),
  CONSTRAINT uq_activity_context UNIQUE (graph_id, context_occurrence_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Canonical ordered details. Native action detail indices and evidence remain unchanged.
CREATE TABLE `activity_detail` (
  `graph_id` VARCHAR(128) NOT NULL,
  `activity_id` VARCHAR(128) NOT NULL,
  `detail_index` INT UNSIGNED NOT NULL,
  `value` TEXT NOT NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  PRIMARY KEY (`graph_id`, `activity_id`, `detail_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Task-specific domain label for one person graph.
CREATE TABLE `domain` (
  `graph_id` VARCHAR(128) NOT NULL,
  `domain_id` VARCHAR(128) NOT NULL,
  `label` TEXT NOT NULL,
  `summary` TEXT NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `domain_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- An ongoing matter organized around the focal person; one primary domain.
CREATE TABLE `event` (
  `graph_id` VARCHAR(128) NOT NULL,
  `event_id` VARCHAR(128) NOT NULL,
  `domain_id` VARCHAR(128) NOT NULL,
  `label` TEXT NOT NULL,
  `summary` TEXT NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Evidence-supported period of the person's involvement. stage_id is local to its event.
CREATE TABLE `stage` (
  `graph_id` VARCHAR(128) NOT NULL,
  `event_id` VARCHAR(128) NOT NULL,
  `stage_id` VARCHAR(128) NOT NULL,
  `label` TEXT NOT NULL,
  `summary` TEXT NULL,
  `boundary_reason` TEXT NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `event_id`, `stage_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- M:N placement; nullable stage permits unsegmented events. It never changes the actor.
CREATE TABLE `event_activity` (
  `graph_id` VARCHAR(128) NOT NULL,
  `event_id` VARCHAR(128) NOT NULL,
  `activity_id` VARCHAR(128) NOT NULL,
  `stage_id` VARCHAR(128) NULL,
  `display_title` TEXT NULL,
  `detail_mode` VARCHAR(16) NOT NULL DEFAULT 'all',
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`graph_id`, `event_id`, `activity_id`),
  CONSTRAINT ck_detail_mode CHECK (detail_mode IN ('all','selected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Optional selection of existing detail rows for one placement, with FKs to both sides.
CREATE TABLE `event_activity_detail` (
  `graph_id` VARCHAR(128) NOT NULL,
  `event_id` VARCHAR(128) NOT NULL,
  `activity_id` VARCHAR(128) NOT NULL,
  `detail_index` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`graph_id`, `event_id`, `activity_id`, `detail_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- Graph-wide semantic edge between canonical activities; evidence for the edge is separate from endpoint evidence.
CREATE TABLE `activity_relation` (
  `graph_id` VARCHAR(128) NOT NULL,
  `link_id` VARCHAR(128) NOT NULL,
  `from_activity_id` VARCHAR(128) NOT NULL,
  `to_activity_id` VARCHAR(128) NOT NULL,
  `relation_type` VARCHAR(32) NOT NULL,
  `description` TEXT NULL,
  `basis` VARCHAR(16) NOT NULL,
  `evidence_set_id` VARCHAR(128) NULL,
  PRIMARY KEY (`graph_id`, `link_id`),
  CONSTRAINT ck_link_not_self CHECK (from_activity_id <> to_activity_id),
  CONSTRAINT ck_activity_relation_type CHECK (relation_type IN ('precedes','overlaps','executed_by','explains','responds_to','context_for')),
  CONSTRAINT ck_relation_basis CHECK (basis IN ('source','inferred','temporal')),
  CONSTRAINT ck_semantic_link_evidence CHECK (relation_type IN ('precedes','overlaps') OR evidence_set_id IS NOT NULL),
  CONSTRAINT uq_activity_link UNIQUE (graph_id, from_activity_id, to_activity_id, relation_type),
  CONSTRAINT ck_temporal_basis CHECK (basis <> 'temporal' OR relation_type IN ('precedes','overlaps'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

ALTER TABLE `entity` ADD CONSTRAINT `fk_01_entity`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `occurrence` ADD CONSTRAINT `fk_02_occurrence`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `source_document` ADD CONSTRAINT `fk_03_source_document`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `evidence_span` ADD CONSTRAINT `fk_04_evidence_span`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `evidence_set` ADD CONSTRAINT `fk_05_evidence_set`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `time_value` ADD CONSTRAINT `fk_06_time_value`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `subject_graph` ADD CONSTRAINT `fk_07_subject_graph`
  FOREIGN KEY (`graph_id`, `subject_entity_id`) REFERENCES `entity` (`graph_id`, `entity_id`)
;
ALTER TABLE `entity_alias` ADD CONSTRAINT `fk_08_entity_alias`
  FOREIGN KEY (`graph_id`, `entity_id`) REFERENCES `entity` (`graph_id`, `entity_id`)
;
ALTER TABLE `occurrence_participant` ADD CONSTRAINT `fk_09_occurrence_participant`
  FOREIGN KEY (`graph_id`, `occurrence_id`) REFERENCES `occurrence` (`graph_id`, `occurrence_id`)
;
ALTER TABLE `occurrence_participant` ADD CONSTRAINT `fk_10_occurrence_participant`
  FOREIGN KEY (`graph_id`, `entity_id`) REFERENCES `entity` (`graph_id`, `entity_id`)
;
ALTER TABLE `participation` ADD CONSTRAINT `fk_11_participation`
  FOREIGN KEY (`graph_id`, `occurrence_id`, `entity_id`) REFERENCES `occurrence_participant` (`graph_id`, `occurrence_id`, `entity_id`)
;
ALTER TABLE `action` ADD CONSTRAINT `fk_12_action`
  FOREIGN KEY (`graph_id`, `occurrence_id`, `actor_id`) REFERENCES `occurrence_participant` (`graph_id`, `occurrence_id`, `entity_id`)
;
ALTER TABLE `financial_transaction` ADD CONSTRAINT `fk_13_financial_transaction`
  FOREIGN KEY (`graph_id`, `occurrence_id`) REFERENCES `occurrence` (`graph_id`, `occurrence_id`)
;
ALTER TABLE `financial_transaction` ADD CONSTRAINT `fk_14_financial_transaction`
  FOREIGN KEY (`graph_id`, `occurrence_id`, `from_entity_id`) REFERENCES `occurrence_participant` (`graph_id`, `occurrence_id`, `entity_id`)
;
ALTER TABLE `financial_transaction` ADD CONSTRAINT `fk_15_financial_transaction`
  FOREIGN KEY (`graph_id`, `occurrence_id`, `to_entity_id`) REFERENCES `occurrence_participant` (`graph_id`, `occurrence_id`, `entity_id`)
;
ALTER TABLE `transaction_instrument` ADD CONSTRAINT `fk_16_transaction_instrument`
  FOREIGN KEY (`graph_id`, `transaction_id`) REFERENCES `financial_transaction` (`graph_id`, `transaction_id`)
;
ALTER TABLE `entity_relation` ADD CONSTRAINT `fk_17_entity_relation`
  FOREIGN KEY (`graph_id`, `from_entity_id`) REFERENCES `entity` (`graph_id`, `entity_id`)
;
ALTER TABLE `entity_relation` ADD CONSTRAINT `fk_18_entity_relation`
  FOREIGN KEY (`graph_id`, `to_entity_id`) REFERENCES `entity` (`graph_id`, `entity_id`)
;
ALTER TABLE `relation_occurrence` ADD CONSTRAINT `fk_19_relation_occurrence`
  FOREIGN KEY (`graph_id`, `relation_id`) REFERENCES `entity_relation` (`graph_id`, `relation_id`)
;
ALTER TABLE `relation_occurrence` ADD CONSTRAINT `fk_20_relation_occurrence`
  FOREIGN KEY (`graph_id`, `occurrence_id`) REFERENCES `occurrence` (`graph_id`, `occurrence_id`)
;
ALTER TABLE `evidence_span` ADD CONSTRAINT `fk_21_evidence_span`
  FOREIGN KEY (`graph_id`, `document_id`) REFERENCES `source_document` (`graph_id`, `document_id`)
;
ALTER TABLE `evidence_link` ADD CONSTRAINT `fk_22_evidence_link`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `evidence_link` ADD CONSTRAINT `fk_23_evidence_link`
  FOREIGN KEY (`graph_id`, `span_id`) REFERENCES `evidence_span` (`graph_id`, `span_id`)
;
ALTER TABLE `subject_graph` ADD CONSTRAINT `fk_24_subject_graph`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `entity` ADD CONSTRAINT `fk_25_entity`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `occurrence` ADD CONSTRAINT `fk_26_occurrence`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `participation` ADD CONSTRAINT `fk_27_participation`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `action` ADD CONSTRAINT `fk_28_action`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `financial_transaction` ADD CONSTRAINT `fk_29_financial_transaction`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `transaction_instrument` ADD CONSTRAINT `fk_30_transaction_instrument`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `entity_relation` ADD CONSTRAINT `fk_31_entity_relation`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `occurrence` ADD CONSTRAINT `fk_32_occurrence`
  FOREIGN KEY (`graph_id`, `start_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `occurrence` ADD CONSTRAINT `fk_33_occurrence`
  FOREIGN KEY (`graph_id`, `end_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `participation` ADD CONSTRAINT `fk_34_participation`
  FOREIGN KEY (`graph_id`, `start_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `participation` ADD CONSTRAINT `fk_35_participation`
  FOREIGN KEY (`graph_id`, `end_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `action` ADD CONSTRAINT `fk_36_action`
  FOREIGN KEY (`graph_id`, `timestamp_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `financial_transaction` ADD CONSTRAINT `fk_37_financial_transaction`
  FOREIGN KEY (`graph_id`, `timestamp_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `entity_relation` ADD CONSTRAINT `fk_38_entity_relation`
  FOREIGN KEY (`graph_id`, `valid_from_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `entity_relation` ADD CONSTRAINT `fk_39_entity_relation`
  FOREIGN KEY (`graph_id`, `valid_to_time_id`) REFERENCES `time_value` (`graph_id`, `time_id`)
;
ALTER TABLE `occurrence_label` ADD CONSTRAINT `fk_40_occurrence_label`
  FOREIGN KEY (`graph_id`, `occurrence_id`) REFERENCES `occurrence` (`graph_id`, `occurrence_id`)
;
ALTER TABLE `activity` ADD CONSTRAINT `fk_41_activity`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `activity` ADD CONSTRAINT `fk_42_activity`
  FOREIGN KEY (`graph_id`, `action_id`) REFERENCES `action` (`graph_id`, `action_id`)
;
ALTER TABLE `activity` ADD CONSTRAINT `fk_43_activity`
  FOREIGN KEY (`graph_id`, `transaction_id`) REFERENCES `financial_transaction` (`graph_id`, `transaction_id`)
;
ALTER TABLE `activity` ADD CONSTRAINT `fk_44_activity`
  FOREIGN KEY (`graph_id`, `context_occurrence_id`) REFERENCES `occurrence` (`graph_id`, `occurrence_id`)
;
ALTER TABLE `activity_detail` ADD CONSTRAINT `fk_45_activity_detail`
  FOREIGN KEY (`graph_id`, `activity_id`) REFERENCES `activity` (`graph_id`, `activity_id`)
;
ALTER TABLE `activity_detail` ADD CONSTRAINT `fk_46_activity_detail`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `domain` ADD CONSTRAINT `fk_47_domain`
  FOREIGN KEY (`graph_id`) REFERENCES `subject_graph` (`graph_id`)
;
ALTER TABLE `event` ADD CONSTRAINT `fk_48_event`
  FOREIGN KEY (`graph_id`, `domain_id`) REFERENCES `domain` (`graph_id`, `domain_id`)
;
ALTER TABLE `event` ADD CONSTRAINT `fk_49_event`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `stage` ADD CONSTRAINT `fk_50_stage`
  FOREIGN KEY (`graph_id`, `event_id`) REFERENCES `event` (`graph_id`, `event_id`)
;
ALTER TABLE `stage` ADD CONSTRAINT `fk_51_stage`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;
ALTER TABLE `event_activity` ADD CONSTRAINT `fk_52_event_activity`
  FOREIGN KEY (`graph_id`, `event_id`) REFERENCES `event` (`graph_id`, `event_id`)
;
ALTER TABLE `event_activity` ADD CONSTRAINT `fk_53_event_activity`
  FOREIGN KEY (`graph_id`, `activity_id`) REFERENCES `activity` (`graph_id`, `activity_id`)
;
ALTER TABLE `event_activity` ADD CONSTRAINT `fk_54_event_activity`
  FOREIGN KEY (`graph_id`, `event_id`, `stage_id`) REFERENCES `stage` (`graph_id`, `event_id`, `stage_id`)
;
ALTER TABLE `event_activity_detail` ADD CONSTRAINT `fk_55_event_activity_detail`
  FOREIGN KEY (`graph_id`, `event_id`, `activity_id`) REFERENCES `event_activity` (`graph_id`, `event_id`, `activity_id`)
;
ALTER TABLE `event_activity_detail` ADD CONSTRAINT `fk_56_event_activity_detail`
  FOREIGN KEY (`graph_id`, `activity_id`, `detail_index`) REFERENCES `activity_detail` (`graph_id`, `activity_id`, `detail_index`)
;
ALTER TABLE `activity_relation` ADD CONSTRAINT `fk_57_activity_relation`
  FOREIGN KEY (`graph_id`, `from_activity_id`) REFERENCES `activity` (`graph_id`, `activity_id`)
;
ALTER TABLE `activity_relation` ADD CONSTRAINT `fk_58_activity_relation`
  FOREIGN KEY (`graph_id`, `to_activity_id`) REFERENCES `activity` (`graph_id`, `activity_id`)
;
ALTER TABLE `activity_relation` ADD CONSTRAINT `fk_59_activity_relation`
  FOREIGN KEY (`graph_id`, `evidence_set_id`) REFERENCES `evidence_set` (`graph_id`, `evidence_set_id`)
;

-- Dereference the canonical fact and retain original actors, parties and occurrence context.
CREATE VIEW `v_activity_facts` AS
SELECT a.graph_id, a.activity_id, 'action' AS fact_type, x.action_id AS fact_id,
 x.occurrence_id, x.actor_id, NULL AS from_entity_id, NULL AS to_entity_id,
 x.action_type AS title, x.timestamp_time_id AS start_time_id, x.timestamp_time_id AS end_time_id, x.evidence_set_id
FROM activity a JOIN action x ON x.graph_id=a.graph_id AND x.action_id=a.action_id
UNION ALL
SELECT a.graph_id,a.activity_id,'transaction',t.transaction_id,t.occurrence_id,NULL,t.from_entity_id,t.to_entity_id,
 t.name,t.timestamp_time_id,t.timestamp_time_id,t.evidence_set_id
FROM activity a JOIN financial_transaction t ON t.graph_id=a.graph_id AND t.transaction_id=a.transaction_id
UNION ALL
SELECT a.graph_id,a.activity_id,'context',e.occurrence_id,e.occurrence_id,NULL,NULL,NULL,e.title,e.start_time_id,e.end_time_id,e.evidence_set_id
FROM activity a JOIN occurrence e ON e.graph_id=a.graph_id AND e.occurrence_id=a.context_occurrence_id;

-- One row per event/activity placement, with typed hierarchy; no organization decisions in the renderer.
CREATE VIEW `v_person_timeline` AS
SELECT g.graph_id,g.subject_entity_id,p.name AS person_name,
 d.domain_id,d.label AS domain_label,d.sort_order AS domain_order,
 s.event_id,s.label AS event_label,s.summary AS event_summary,s.sort_order AS event_order,
 st.stage_id,st.label AS stage_label,st.summary AS stage_summary,st.boundary_reason,st.sort_order AS stage_order,
 sa.activity_id,sa.sort_order AS activity_order,sa.detail_mode,COALESCE(sa.display_title,f.title) AS display_title,
 f.fact_type,f.fact_id,f.occurrence_id,f.actor_id,f.from_entity_id,f.to_entity_id,
 e.title AS occurrence_title,COALESCE(el.label,e.title) AS occurrence_display_label,e.descriptions AS occurrence_descriptions,e.subject_relevance,
 f.start_time_id,f.end_time_id,ts.value AS start_value,te.value AS end_value,
 ts.window_start AS start_window_start,ts.window_end AS start_window_end,
 ts.original_text AS start_original_text,ts.is_approximate AS start_is_approximate,ts.window_semantics AS start_window_semantics,
 te.window_start AS end_window_start,te.window_end AS end_window_end,
 te.original_text AS end_original_text,te.is_approximate AS end_is_approximate,te.window_semantics AS end_window_semantics,f.evidence_set_id,
 CASE WHEN f.actor_id=g.subject_entity_id THEN 'personal' WHEN f.fact_type='action' THEN 'other_actor' WHEN f.fact_type='transaction' THEN 'transaction' ELSE 'context' END AS activity_role
FROM event_activity sa
JOIN event s ON s.graph_id=sa.graph_id AND s.event_id=sa.event_id
JOIN domain d ON d.graph_id=s.graph_id AND d.domain_id=s.domain_id
JOIN subject_graph g ON g.graph_id=sa.graph_id
JOIN entity p ON p.graph_id=g.graph_id AND p.entity_id=g.subject_entity_id
LEFT JOIN stage st ON st.graph_id=sa.graph_id AND st.event_id=sa.event_id AND st.stage_id=sa.stage_id
JOIN v_activity_facts f ON f.graph_id=sa.graph_id AND f.activity_id=sa.activity_id
JOIN occurrence e ON e.graph_id=f.graph_id AND e.occurrence_id=f.occurrence_id
LEFT JOIN occurrence_label el ON el.graph_id=e.graph_id AND el.occurrence_id=e.occurrence_id
LEFT JOIN time_value ts ON ts.graph_id=f.graph_id AND ts.time_id=f.start_time_id
LEFT JOIN time_value te ON te.graph_id=f.graph_id AND te.time_id=f.end_time_id;

-- All or explicitly selected details for each placement.
CREATE VIEW `v_activity_hover_details` AS
SELECT sa.graph_id,sa.event_id,sa.activity_id,d.detail_index,d.value,d.evidence_set_id
FROM event_activity sa JOIN activity_detail d ON d.graph_id=sa.graph_id AND d.activity_id=sa.activity_id
WHERE sa.detail_mode='all' OR EXISTS
 (SELECT 1 FROM event_activity_detail sd WHERE sd.graph_id=sa.graph_id AND sd.event_id=sa.event_id AND sd.activity_id=sa.activity_id AND sd.detail_index=d.detail_index);

-- Edges whose two endpoints belong to the same event. Cross-event edges remain in activity_relation.
CREATE VIEW `v_event_links` AS
SELECT l.graph_id,a.event_id,l.link_id,l.from_activity_id,l.to_activity_id,l.relation_type,l.description,l.basis,l.evidence_set_id
FROM activity_relation l
JOIN event_activity a ON a.graph_id=l.graph_id AND a.activity_id=l.from_activity_id
JOIN event_activity b ON b.graph_id=l.graph_id AND b.activity_id=l.to_activity_id AND b.event_id=a.event_id;

-- Distinct occurrence-context entity relations; there is no joint-participation requirement.
CREATE VIEW `v_event_entity_relations` AS
SELECT DISTINCT sa.graph_id,sa.event_id,r.relation_id,r.from_entity_id,r.to_entity_id,r.relation_type,r.valid_from_time_id,r.valid_to_time_id,r.evidence_set_id
FROM event_activity sa
JOIN v_activity_facts f ON f.graph_id=sa.graph_id AND f.activity_id=sa.activity_id
JOIN relation_occurrence re ON re.graph_id=f.graph_id AND re.occurrence_id=f.occurrence_id
JOIN entity_relation r ON r.graph_id=re.graph_id AND r.relation_id=re.relation_id;

-- Field-specific evidence and known source locations.
CREATE VIEW `v_evidence` AS
SELECT l.graph_id,l.evidence_set_id,l.field_path,l.quote_order,s.span_id,s.quote,s.document_id,s.char_start,s.char_end,d.source_url,d.title AS source_title,d.published_at
FROM evidence_link l JOIN evidence_span s ON s.graph_id=l.graph_id AND s.span_id=l.span_id
LEFT JOIN source_document d ON d.graph_id=s.graph_id AND d.document_id=s.document_id;
