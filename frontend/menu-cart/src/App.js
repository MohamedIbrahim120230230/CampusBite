import { useState } from 'react';
import MenuPage from './MenuPage';
import AdminPanel from './AdminPanel';

function App() {
  const [page, setPage] = useState('menu');

  return (
    <div>
      <nav className="navbar navbar-dark bg-dark px-4">
        <span className="navbar-brand">🍴 Cafeteria System</span>
        <div>
          <button className={`btn me-2 ${page === 'menu' ? 'btn-light' : 'btn-outline-light'}`}
            onClick={() => setPage('menu')}>Menu</button>
          <button className={`btn ${page === 'admin' ? 'btn-light' : 'btn-outline-light'}`}
            onClick={() => setPage('admin')}>Admin</button>
        </div>
      </nav>
      {page === 'menu' ? <MenuPage /> : <AdminPanel />}
    </div>
  );
}

export default App;