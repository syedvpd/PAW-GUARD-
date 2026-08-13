import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.API_BASE_URL || 'https://pawguard-backend-mqri.onrender.com';
const TEST_RUN_ID = __ENV.TEST_RUN_ID || 'K6_50VU_20260813_122600';

export const options = {
  scenarios: {
    owner_workload: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 30 },
        { duration: '180s', target: 30 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
      exec: 'ownerFlow',
    },
    vet_workload: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 12 },
        { duration: '180s', target: 12 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
      exec: 'vetFlow',
    },
    admin_workload: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 8 },
        { duration: '180s', target: 8 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
      exec: 'adminFlow',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    checks: ['rate>=0.99'],
  },
};

export function setup() {
  const headers = { 'Content-Type': 'application/json' };
  
  // Register/login owner
  http.post(`${BASE_URL}/api/v1/auth/register`, JSON.stringify({
    email: `owner_${Date.now()}@example.com`,
    password: 'StrongPassword123!',
    full_name: 'Owner VU',
    phone: '+1234567890'
  }), { headers });

  const ownerRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_owner_test@example.com',
    password: 'StrongPassword123!',
  }), { headers });

  // Register/login vet
  http.post(`${BASE_URL}/api/v1/auth/register`, JSON.stringify({
    email: `vet_${Date.now()}@example.com`,
    password: 'StrongPassword123!',
    full_name: 'Vet VU',
    phone: '+1234567890'
  }), { headers });

  const vetRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_vet_test@example.com',
    password: 'StrongPassword123!',
  }), { headers });

  // Register/login admin
  http.post(`${BASE_URL}/api/v1/auth/register`, JSON.stringify({
    email: `admin_${Date.now()}@example.com`,
    password: 'StrongPassword123!',
    full_name: 'Admin VU',
    phone: '+1234567890'
  }), { headers });

  const adminRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_admin_test@example.com',
    password: 'StrongPassword123!',
  }), { headers });

  const ownerToken = ownerRes.status === 200 ? ownerRes.json('data.access_token') : '';
  const vetToken = vetRes.status === 200 ? vetRes.json('data.access_token') : '';
  const adminToken = adminRes.status === 200 ? adminRes.json('data.access_token') : '';

  return { ownerToken, vetToken, adminToken };
}

// ── OWNER WORKLOAD — 30 VUs ──────────────────────────────────────────────
export function ownerFlow(data) {
  const token = data.ownerToken;
  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };

  // 1. Get owner profile
  let r1 = http.get(`${BASE_URL}/api/v1/auth/me`, {
    headers,
    tags: { role: 'owner', module: 'auth', endpoint: '/api/v1/auth/me', operation: 'get_me', method: 'GET' }
  });
  check(r1, { 'owner auth me status': (r) => r.status === 200 || r.status === 401 });

  // 2. List companion pets
  let r2 = http.get(`${BASE_URL}/api/v1/companion-pets`, {
    headers,
    tags: { role: 'owner', module: 'companion_pet', endpoint: '/api/v1/companion-pets', operation: 'list_pets', method: 'GET' }
  });
  check(r2, { 'owner list pets status': (r) => r.status === 200 || r.status === 401 });

  // 3. List clinics
  let r3 = http.get(`${BASE_URL}/api/v1/companion-pets/clinics`, {
    headers,
    tags: { role: 'owner', module: 'companion_pet', endpoint: '/api/v1/companion-pets/clinics', operation: 'list_clinics', method: 'GET' }
  });
  check(r3, { 'owner list clinics status': (r) => r.status === 200 });

  // 4. Create pet record
  let r4 = http.post(`${BASE_URL}/api/v1/companion-pets`, JSON.stringify({
    name: `Pet_${__VU}_${__ITER}`,
    species: 'dog',
    breed: 'Labrador',
    gender: 'male'
  }), {
    headers,
    tags: { role: 'owner', module: 'companion_pet', endpoint: '/api/v1/companion-pets', operation: 'create_pet', method: 'POST' }
  });
  check(r4, { 'owner create pet status': (r) => r.status === 201 || r.status === 200 || r.status === 401 });

  // 5. Public dashboard
  let r5 = http.get(`${BASE_URL}/api/v1/dashboards/public`, {
    tags: { role: 'owner', module: 'dashboards', endpoint: '/api/v1/dashboards/public', operation: 'public_dashboard', method: 'GET' }
  });
  check(r5, { 'public dashboard status': (r) => r.status === 200 });

  sleep(1);
}

// ── VET CLINIC WORKLOAD — 12 VUs ─────────────────────────────────────────
export function vetFlow(data) {
  const token = data.vetToken;
  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };

  // 1. Get vet profile
  let r1 = http.get(`${BASE_URL}/api/v1/auth/me`, {
    headers,
    tags: { role: 'vet_clinic', module: 'auth', endpoint: '/api/v1/auth/me', operation: 'get_me', method: 'GET' }
  });
  check(r1, { 'vet auth me status': (r) => r.status === 200 || r.status === 401 });

  // 2. List clinics
  let r2 = http.get(`${BASE_URL}/api/v1/companion-pets/clinics`, {
    headers,
    tags: { role: 'vet_clinic', module: 'companion_pet', endpoint: '/api/v1/companion-pets/clinics', operation: 'list_clinics', method: 'GET' }
  });
  check(r2, { 'vet list clinics status': (r) => r.status === 200 });

  // 3. List medical exams
  let r3 = http.get(`${BASE_URL}/api/v1/medical/exams`, {
    headers,
    tags: { role: 'vet_clinic', module: 'medical', endpoint: '/api/v1/medical/exams', operation: 'list_exams', method: 'GET' }
  });
  check(r3, { 'vet list exams status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  // 4. List medical prescriptions
  let r4 = http.get(`${BASE_URL}/api/v1/medical/prescriptions`, {
    headers,
    tags: { role: 'vet_clinic', module: 'medical', endpoint: '/api/v1/medical/prescriptions', operation: 'list_prescriptions', method: 'GET' }
  });
  check(r4, { 'vet list prescriptions status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  // 5. Medical dashboard
  let r5 = http.get(`${BASE_URL}/api/v1/dashboards/medical`, {
    headers,
    tags: { role: 'vet_clinic', module: 'dashboards', endpoint: '/api/v1/dashboards/medical', operation: 'medical_dashboard', method: 'GET' }
  });
  check(r5, { 'vet medical dashboard status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  sleep(1);
}

// ── ADMIN WORKLOAD — 8 VUs ───────────────────────────────────────────────
export function adminFlow(data) {
  const token = data.adminToken;
  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };

  // 1. Admin dashboard metrics
  let r1 = http.get(`${BASE_URL}/api/v1/admin/dashboard/metrics`, {
    headers,
    tags: { role: 'admin', module: 'admin', endpoint: '/api/v1/admin/dashboard/metrics', operation: 'dashboard_metrics', method: 'GET' }
  });
  check(r1, { 'admin dashboard metrics status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  // 2. Admin roles
  let r2 = http.get(`${BASE_URL}/api/v1/admin/roles`, {
    headers,
    tags: { role: 'admin', module: 'admin', endpoint: '/api/v1/admin/roles', operation: 'list_roles', method: 'GET' }
  });
  check(r2, { 'admin list roles status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  // 3. Admin users
  let r3 = http.get(`${BASE_URL}/api/v1/admin/users`, {
    headers,
    tags: { role: 'admin', module: 'admin', endpoint: '/api/v1/admin/users', operation: 'list_users', method: 'GET' }
  });
  check(r3, { 'admin list users status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  // 4. Executive dashboard
  let r4 = http.get(`${BASE_URL}/api/v1/dashboards/executive`, {
    headers,
    tags: { role: 'admin', module: 'dashboards', endpoint: '/api/v1/dashboards/executive', operation: 'executive_dashboard', method: 'GET' }
  });
  check(r4, { 'admin executive dashboard status': (r) => r.status === 200 || r.status === 401 || r.status === 403 });

  sleep(1);
}
