-- Phase 9.3e pagination verification seed
-- Purpose: create enough published article records to verify page=2 and page=999 behavior.
-- Safe to re-run: existing records with slug prefix phase9-3e-pagination-test- are removed first.

START TRANSACTION;

SET @slug_prefix := 'phase9-3e-pagination-test-';
SET @article_type := 'diary';
SET @language_code := 'ja';
SET @category_term_key := 'pagination-test-category';
SET @category_slug := 'pagination-test-category';
SET @tag_term_key := 'pagination-test-tag';
SET @tag_slug := 'pagination-test-tag';

-- Cleanup previous test articles.
DROP TEMPORARY TABLE IF EXISTS tmp_phase9_3e_pagination_content_ids;
CREATE TEMPORARY TABLE tmp_phase9_3e_pagination_content_ids (id INT UNSIGNED PRIMARY KEY);

INSERT INTO tmp_phase9_3e_pagination_content_ids (id)
SELECT id
FROM tb_content
WHERE content_type = 'article'
  AND slug LIKE CONCAT(@slug_prefix, '%');

DELETE ctt
FROM tb_content_taxonomy_term AS ctt
INNER JOIN tmp_phase9_3e_pagination_content_ids AS tmp ON tmp.id = ctt.content_id;

DELETE ca
FROM tb_content_article AS ca
INNER JOIN tmp_phase9_3e_pagination_content_ids AS tmp ON tmp.id = ca.content_id;

DELETE tr
FROM tb_content_translation AS tr
INNER JOIN tmp_phase9_3e_pagination_content_ids AS tmp ON tmp.id = tr.content_id;

DELETE c
FROM tb_content AS c
INNER JOIN tmp_phase9_3e_pagination_content_ids AS tmp ON tmp.id = c.id;

-- Resolve required master records.
SET @article_type_id := (
  SELECT id
  FROM tb_article_type
  WHERE article_type = @article_type
    AND is_active = 1
  LIMIT 1
);

SET @category_vocabulary_id := (
  SELECT id
  FROM tb_taxonomy_vocabulary
  WHERE vocabulary_key = 'category'
  LIMIT 1
);

SET @tag_vocabulary_id := (
  SELECT id
  FROM tb_taxonomy_vocabulary
  WHERE vocabulary_key = 'tag'
  LIMIT 1
);

-- Fail fast when required master data is missing.
SET @missing_message := CONCAT(
  IF(@article_type_id IS NULL, 'missing active tb_article_type.diary; ', ''),
  IF(@category_vocabulary_id IS NULL, 'missing tb_taxonomy_vocabulary.category; ', ''),
  IF(@tag_vocabulary_id IS NULL, 'missing tb_taxonomy_vocabulary.tag; ', '')
);

SET @check_required_seed_data := IF(@missing_message = '', 1, 0);

-- MySQL/MariaDB cannot SIGNAL dynamically without a stored program in some versions.
-- This SELECT intentionally raises an error if required master data is missing.
SELECT 1 / @check_required_seed_data AS required_seed_data_check;

-- Ensure dedicated category/tag terms exist.
INSERT INTO tb_taxonomy_term (vocabulary_id, parent_id, term_key, slug, status, is_indexable, sort_order)
SELECT @category_vocabulary_id, NULL, @category_term_key, @category_slug, 'active', 1, 9900
WHERE NOT EXISTS (
  SELECT 1 FROM tb_taxonomy_term WHERE vocabulary_id = @category_vocabulary_id AND term_key = @category_term_key AND deleted_at IS NULL
);

SET @category_term_id := (
  SELECT id
  FROM tb_taxonomy_term
  WHERE vocabulary_id = @category_vocabulary_id
    AND term_key = @category_term_key
    AND deleted_at IS NULL
  LIMIT 1
);

INSERT INTO tb_taxonomy_term (vocabulary_id, parent_id, term_key, slug, status, is_indexable, sort_order)
SELECT @tag_vocabulary_id, NULL, @tag_term_key, @tag_slug, 'active', 1, 9901
WHERE NOT EXISTS (
  SELECT 1 FROM tb_taxonomy_term WHERE vocabulary_id = @tag_vocabulary_id AND term_key = @tag_term_key AND deleted_at IS NULL
);

SET @tag_term_id := (
  SELECT id
  FROM tb_taxonomy_term
  WHERE vocabulary_id = @tag_vocabulary_id
    AND term_key = @tag_term_key
    AND deleted_at IS NULL
  LIMIT 1
);

INSERT INTO tb_taxonomy_term_translation (term_id, language_code, name, description, meta_title, meta_description)
VALUES
  (@category_term_id, @language_code, 'Pagination Test Category', 'Phase 9.3e pagination verification category.', 'Pagination Test Category', 'Phase 9.3e pagination verification category.'),
  (@tag_term_id, @language_code, 'Pagination Test Tag', 'Phase 9.3e pagination verification tag.', 'Pagination Test Tag', 'Phase 9.3e pagination verification tag.')
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  description = VALUES(description),
  meta_title = VALUES(meta_title),
  meta_description = VALUES(meta_description),
  updated_at = CURRENT_TIMESTAMP;

-- Create 30 published article records. 30 records produce page=2 with per_page=20.
DROP TEMPORARY TABLE IF EXISTS tmp_phase9_3e_pagination_numbers;
CREATE TEMPORARY TABLE tmp_phase9_3e_pagination_numbers (n INT UNSIGNED PRIMARY KEY);

INSERT INTO tmp_phase9_3e_pagination_numbers (n) VALUES
  (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),
  (11),(12),(13),(14),(15),(16),(17),(18),(19),(20),
  (21),(22),(23),(24),(25),(26),(27),(28),(29),(30);

INSERT INTO tb_content (content_type, slug, status, published_at, author_id, created_at, updated_at, deleted_at)
SELECT
  'article',
  CONCAT(@slug_prefix, LPAD(n, 2, '0')),
  'published',
  DATE_SUB(NOW(), INTERVAL n DAY),
  NULL,
  NOW(),
  NOW(),
  NULL
FROM tmp_phase9_3e_pagination_numbers;

INSERT INTO tb_content_article (content_id, article_type_id, created_at, updated_at)
SELECT c.id, @article_type_id, NOW(), NOW()
FROM tb_content AS c
WHERE c.content_type = 'article'
  AND c.slug LIKE CONCAT(@slug_prefix, '%');

INSERT INTO tb_content_translation (content_id, language_code, title, body, meta_title, meta_description, created_at, updated_at)
SELECT
  c.id,
  @language_code,
  CONCAT('[pagination-test] Article ', SUBSTRING(c.slug, CHAR_LENGTH(@slug_prefix) + 1)),
  CONCAT('Phase 9.3e pagination verification body for ', c.slug, '.'),
  CONCAT('[pagination-test] Article ', SUBSTRING(c.slug, CHAR_LENGTH(@slug_prefix) + 1)),
  CONCAT('Phase 9.3e pagination verification meta description for ', c.slug, '.'),
  NOW(),
  NOW()
FROM tb_content AS c
WHERE c.content_type = 'article'
  AND c.slug LIKE CONCAT(@slug_prefix, '%');

INSERT INTO tb_content_taxonomy_term (content_id, term_id, is_primary, sort_order)
SELECT c.id, @category_term_id, 1, 0
FROM tb_content AS c
WHERE c.content_type = 'article'
  AND c.slug LIKE CONCAT(@slug_prefix, '%')
UNION ALL
SELECT c.id, @tag_term_id, 0, 1
FROM tb_content AS c
WHERE c.content_type = 'article'
  AND c.slug LIKE CONCAT(@slug_prefix, '%');

SELECT
  COUNT(*) AS seeded_article_count,
  @article_type AS article_type,
  @category_slug AS category_slug,
  @tag_slug AS tag_slug
FROM tb_content
WHERE content_type = 'article'
  AND slug LIKE CONCAT(@slug_prefix, '%');

COMMIT;
