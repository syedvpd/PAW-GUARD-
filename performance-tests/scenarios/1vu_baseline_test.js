import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.API_BASE_URL || 'https://pawguard-backend-mqri.onrender.com';

export const options = {
  scenarios: {
    baseline: {
      executor: 'constant-vus',
      vus: 1,
      duration: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
  },
};

export function setup() {
  const headers = { 'Content-Type': 'application/json' };
  
  // Login owner
  const ownerRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_owner_test@example.com',
    password: 'StrongPassword123!',
  }), { headers: headers, tags: { role: 'owner', module: 'auth', endpoint: '/api/v1/auth/login', operation: 'login', method: 'POST' } });
  
  // Login vet
  const vetRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_vet_test@example.com',
    password: 'StrongPassword123!',
  }), { headers: headers, tags: { role: 'vet', module: 'auth', endpoint: '/api/v1/auth/login', operation: 'login', method: 'POST' } });

  // Login admin
  const adminRes = http.post(`${BASE_URL}/api/v1/auth/login`, JSON.stringify({
    email: 'perf_admin_test@example.com',
    password: 'StrongPassword123!',
  }), { headers: headers, tags: { role: 'admin', module: 'auth', endpoint: '/api/v1/auth/login', operation: 'login', method: 'POST' } });

  const ownerToken = ownerRes.status === 200 ? ownerRes.json('data.access_token') : null;
  const vetToken = vetRes.status === 200 ? vetRes.json('data.access_token') : null;
  const adminToken = adminRes.status === 200 ? adminRes.json('data.access_token') : null;

  return { ownerToken, vetToken, adminToken };
}

export default function (data) {
  const params = (token, role, module, endpoint, operation) => ({
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    tags: { role, module, endpoint, operation, method: 'GET' },
  });

  // Owner 1-VU baseline
  if (data.ownerToken) {
    const res1 = http.get(`${BASE_URL}/api/v1/companion-pets`, params(data.ownerToken, 'owner', 'companion_pet', '/api/v1/companion-pets', 'list_pets'));
    check(res1, { 'owner list pets 200': (r) => r.status === 200 });

    const res2 = http.get(`${BASE_URL}/api/v1/companion-pets/clinics`, params(data.ownerToken, 'owner', 'companion_pet', '/api/v1/companion-pets/clinics', 'list_clinics'));
    check(res2, { 'owner list clinics 200': (r) => r.status === 200 });
  }

  // Vet 1-VU baseline
  if (data.vetToken) {
    const res3 = http.get(`${BASE_URL}/api/v1/medical/exams`, params(data.vetToken, 'vet', 'medical', '/api/v1/medical/exams', 'list_exams'));
    check(res3, { 'vet list exams status': (r) => r.status === 200 || r.status === 403 || r.status === 404 });

    const res4 = http.get(`${BASE_URL}/api/v1/medical/prescriptions`, params(data.vetToken, 'vet', 'medical', '/api/v1/medical/prescriptions', 'list_prescriptions'));
    check(res4, { 'vet list prescriptions status': (r) => r.status === 200 || r.status === 403 || r.status === 404 });
  }

  // Admin 1-VU baseline
  if (data.adminToken) {
    const res5 = http.get(`${BASE_URL}/api/v1/admin/dashboard/summary`, params(data.adminToken, 'admin', 'admin', '/api/v1/admin/dashboard/summary', 'dashboard_summary'));
    check(res5, { 'admin summary status': (r) => r.status === 200 || r.status === 403 || r.status === 404 });

    const res6 = http.get(`${BASE_URL}/api/v1/admin/users`, params(data.adminToken, 'admin', 'admin', '/api/v1/admin/users', 'list_users'));
    check(res6, { 'admin list users status': (r) => r.status === 200 || r.status === 403 });
  }

  sleep(1);
}
