-- Drop if exists (for re-runs)
DROP TABLE IF EXISTS policy;

-- Create table based directly on your JSON structure
CREATE TABLE policy (
  -- top-level
  policy_id                TEXT PRIMARY KEY,

  -- member
  member_full_name         TEXT NOT NULL,
  patient_ssn              TEXT NOT NULL,
  date_of_birth            DATE NOT NULL,

  -- eligibility
  eligibility_active_from  DATE NOT NULL,
  eligibility_active_to    DATE NOT NULL,
  CHECK (eligibility_active_to >= eligibility_active_from),

  -- coverage
  coverage_procedures      TEXT[] NOT NULL,    -- e.g. {'ER visit high complexity','X-ray forearm'}
  coverage_percentage      JSONB NOT NULL,     -- e.g. {"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}

  -- limits
  limits                   JSONB NOT NULL      -- e.g. {"imaging":{"per_year":10}, "er_visit":{"per_year":10}}
);

INSERT INTO policy (
  policy_id,
  member_full_name, patient_ssn, date_of_birth,
  eligibility_active_from, eligibility_active_to,
  coverage_procedures, coverage_percentage, limits
) VALUES
('PPO-ACME-002', 'Anna Smith', '123456789', DATE '1990-05-20',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-003', 'John Doe', '987654321', DATE '1985-02-15',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-004', 'Maria Popescu', '111222333', DATE '1992-07-08',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-005', 'George Ionescu', '444555666', DATE '1988-12-01',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-006', 'Elena Marinescu', '777888999', DATE '1995-03-03',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-007', 'Cristian Dobre', '222333444', DATE '1983-09-25',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-008', 'Ioana Radu', '555666777', DATE '1998-06-18',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-009', 'Andrei Matei', '888999000', DATE '1991-11-30',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb),

('PPO-ACME-010', 'Laura Dumitrescu', '333444555', DATE '1987-04-22',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{"<=500":100, ">500 && <1000":80, ">1000 && <=2000":50, ">2000":30}'::jsonb,
  '{"imaging":{"per_year":10}, "er_visit":{"per_year":10}}'::jsonb);

INSERT INTO policy (
  policy_id,
  member_full_name, patient_ssn, date_of_birth,
  eligibility_active_from, eligibility_active_to,
  coverage_procedures, coverage_percentage, limits
) VALUES (
  'PPO-ACME-001',
  'Mark Johnson', '328291609', DATE '1989-03-11',
  DATE '2025-01-01', DATE '2025-12-31',
  ARRAY['ER visit high complexity','X-ray forearm'],
  '{
     "<=500": 100,
     ">500 && <1000": 80,
     ">1000 && <=2000": 50,
     ">2000": 30
   }'::jsonb,
  '{
     "imaging":  {"per_year": 10},
     "er_visit": {"per_year": 10}
   }'::jsonb
);


SELECT * FROM policy;

SELECT policy_id, member_full_name, patient_ssn, date_of_birth
FROM policy;


DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
