/**
 * Performance Tests — NFR01, NFR02, NFR04, NFR09, NFR10, NFR11
 * Order load test, payment stress, and search performance.
 *
 * Tool: k6  (https://k6.io)
 * Run:  k6 run order-load.js
 *       k6 run payment-stress.js
 *       k6 run search-load.js
 */

// ============================================================
// order-load.js — NFR09, NFR10: 200 concurrent users, 10k orders/day
// ============================================================
import http  from 'k6/http';
import { sleep, check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate        = new Rate('errors');
const orderPlacedTrend = new Trend('order_placed_duration');

export let options = {
  stages: [
    { duration: '30s', target: 50  },   // ramp up
    { duration: '60s', target: 200 },   // peak lunch: 200 concurrent users (NFR09)
    { duration: '30s', target: 0   },   // ramp down
  ],
  thresholds: {
    // NFR02 (refined): Order placement API ≤ 300 ms at p95
    'order_placed_duration': ['p(95)<300'],
    // Error rate must stay below 1%
    'errors':                ['rate<0.01'],
    // HTTP failure rate
    'http_req_failed':       ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

function getAuthToken() {
  const res = http.post(`${BASE_URL}/auth/login`, JSON.stringify({
    email:    'load_test_student@university.edu',
    password: 'LoadTest123!',
  }), { headers: { 'Content-Type': 'application/json' } });
  return res.json('access_token');
}

export default function () {
  const token   = getAuthToken();
  const headers = {
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${token}`,
  };

  // Step 1: Browse menu
  const menuRes = http.get(`${BASE_URL}/menu`, { headers });
  check(menuRes, {
    'menu status 200':      (r) => r.status === 200,
    // NFR01 (refined): Menu page loads ≤ 500 ms at p95
    'menu under 500ms p95': (r) => r.timings.duration < 500,
  });

  // Step 2: Place an order
  const orderStart = Date.now();
  const orderRes = http.post(`${BASE_URL}/orders`, JSON.stringify({
    cart_id:         `cart-load-${__VU}-${__ITER}`,
    idempotency_key: `idem-${__VU}-${__ITER}-${Date.now()}`,
  }), { headers });

  orderPlacedTrend.add(Date.now() - orderStart);

  const orderOk = check(orderRes, {
    'order placed':            (r) => r.status === 200 || r.status === 201,
    'order has id':            (r) => r.json('order_id') !== undefined,
    'order status is PLACED':  (r) => r.json('status') === 'PLACED',
  });
  errorRate.add(!orderOk);

  sleep(1);
}
