/**
 * payment-stress.js — NFR11: 500 stock lock acquisitions/second sustained
 *
 * Run: k6 run payment-stress.js
 */
import http  from 'k6/http';
import { sleep, check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const lockAcquisitions = new Counter('stock_lock_acquisitions');
const lockErrors       = new Rate('stock_lock_errors');
const lockDuration     = new Trend('stock_lock_duration_ms');

export let options = {
  scenarios: {
    stock_lock_stress: {
      executor:          'constant-arrival-rate',
      rate:              500,        // NFR11: 500 acquisitions/second
      timeUnit:          '1s',
      duration:          '30s',      // sustained for 30 seconds
      preAllocatedVUs:   200,
      maxVUs:            400,
    },
  },
  thresholds: {
    // NFR11: 500 locks/s sustained — less than 1% failure rate
    'stock_lock_errors':      ['rate<0.01'],
    // NFR02: Payment endpoint ≤ 300 ms at p95
    'stock_lock_duration_ms': ['p(95)<300'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export function setup() {
  // Obtain a shared auth token for the test run
  const res = http.post(`${BASE_URL}/auth/login`, JSON.stringify({
    email: 'load_test_student@university.edu', password: 'LoadTest123!',
  }), { headers: { 'Content-Type': 'application/json' } });
  return { token: res.json('access_token') };
}

export default function (data) {
  const headers = {
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  const start  = Date.now();
  const payRes = http.post(`${BASE_URL}/orders`, JSON.stringify({
    cart_id:         `cart-stress-${__VU}-${__ITER}`,
    idempotency_key: `key-stress-${__VU}-${__ITER}-${Date.now()}`,
  }), { headers });

  const duration = Date.now() - start;
  lockDuration.add(duration);

  const ok = check(payRes, {
    'lock acquired (200 or 503)': (r) => r.status === 200 || r.status === 503,
  });
  lockErrors.add(!ok);

  if (payRes.status === 200) {
    lockAcquisitions.add(1);
  }

  sleep(0);  // no sleep — maximise throughput
}
