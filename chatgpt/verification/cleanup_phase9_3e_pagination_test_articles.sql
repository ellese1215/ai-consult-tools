-- Phase 9.3e pagination verification cleanup
-- Purpose: remove records created by seed_phase9_3e_pagination_test_articles.sql.

START TRANSACTION;

SET @slug_prefix := 'phase9-3e-pagination-test-';
SET @category_term_key := 'pagination-test-category';
SET @tag_term_key := 'pagination-test-tag';

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

DROP TEMPORARY TABLE IF EXISTS tmp_phase9_3e_pagination_term_ids;
CREATE TEMPORARY TABLE tmp_phase9_3e_pagination_term_ids (id INT UNSIGNED PRIMARY KEY);

INSERT INTO tmp_phase9_3e_pagination_term_ids (id)
SELECT t.id
FROM tb_taxonomy_term AS t
INNER JOIN tb_taxonomy_vocabulary AS v ON v.id = t.vocabulary_id
WHERE (v.vocabulary_key = 'category' AND t.term_key = @category_term_key)
   OR (v.vocabulary_key = 'tag' AND t.term_key = @tag_term_key);

DELETE tr
FROM tb_taxonomy_term_translation AS tr
INNER JOIN tmp_phase9_3e_pagination_term_ids AS tmp ON tmp.id = tr.term_id;

DELETE ctt
FROM tb_content_taxonomy_term AS ctt
INNER JOIN tmp_phase9_3e_pagination_term_ids AS tmp ON tmp.id = ctt.term_id;

DELETE t
FROM tb_taxonomy_term AS t
INNER JOIN tmp_phase9_3e_pagination_term_ids AS tmp ON tmp.id = t.id;

SELECT
  (SELECT COUNT(*) FROM tb_content WHERE content_type = 'article' AND slug LIKE CONCAT(@slug_prefix, '%')) AS remaining_article_count,
  (SELECT COUNT(*) FROM tb_taxonomy_term AS t INNER JOIN tmp_phase9_3e_pagination_term_ids AS tmp ON tmp.id = t.id) AS remaining_term_count;

COMMIT;
