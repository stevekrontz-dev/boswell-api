-- Migration 013: Add 'deleted' status to task_status enum
-- Required for boswell_delete_task endpoint

ALTER TYPE task_status ADD VALUE 'deleted';
