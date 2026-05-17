import React, { useState, useEffect } from 'react';
import { apiFetch } from '../../shared/api'; // Switched to your shared contract utility

export default function AdminPanel() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({
    name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true
  });
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState('');

  useEffect(() => { 
    fetchItems(); 
  }, []);

  // Aligns with Contract 6: Fetch all items for admin parsing
  const fetchItems = async () => {
    try {
      const data = await apiFetch('/menu/items');
      // If backend envelopes data inside a paginated list { items: [], total: X }
      setItems(data.items || data || []);
    } catch (err) {
      console.error('Failed to pull administration menu items:', err);
    }
  };

  const handleChange = e => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm({ ...form, [e.target.name]: val });
  };

  // FR18, FR19 — Create or Update Menu Item configurations via Admin scope
  const handleSubmit = async () => {
    try {
      // Cast numerical inputs correctly before dispatching payloads to the API
      const payload = {
        ...form,
        price: parseFloat(form.price),
        stock_qty: parseInt(form.stock_qty, 10),
        max_order_qty: parseInt(form.max_order_qty, 10)
      };

      if (editingId) {
        // PUT /api/v1/admin/menu/:id
        await apiFetch(`/admin/menu/${editingId}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
        setMessage('Item updated successfully!');
      } else {
        // POST /api/v1/admin/menu
        await apiFetch('/admin/menu', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        setMessage('Item created successfully!');
      }

      setForm({ name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true });
      setEditingId(null);
      fetchItems();
    } catch (err) {
      setMessage(err.message || 'Error saving management item configurations.');
    }
  };

  // FR18 — Load chosen item parameters into interactive inputs
  const handleEdit = (item) => {
    setForm({
      name: item.name,
      category: item.category,
      price: item.price,
      stock_qty: item.stock_qty,
      max_order_qty: item.max_order_qty,
      active: item.active
    });
    setEditingId(item.id);
  };

  // FR18, FR52 — Soft delete / Deactivate item presence from student viewports
  const handleDelete = async (id) => {
    if (!window.confirm('Deactivate this cafeteria menu listing?')) return;
    try {
      // DELETE /api/v1/admin/menu/:id
      await apiFetch(`/admin/menu/${id}`, {
        method: 'DELETE'
      });
      setMessage('Item deactivated successfully.');
      fetchItems();
    } catch (err) {
      setMessage(err.message || 'Failed to deactivate chosen tracking item.');
    }
  };

  return (
    <div className="container mt-4">
      <h2>⚙️ Admin — Menu Management</h2>
      <p className="text-muted">FR18, FR19, FR52 — Create, update, deactivate menu items and set stock/quantity caps</p>

      {message && <div className="alert alert-info">{message}</div>}

      {/* Form Context */}
      <div className="card mb-4">
        <div className="card-header fw-bold">{editingId ? '📝 Edit Menu Item Profile' : '➕ Add New Cafeteria Item'}</div>
        <div className="card-body">
          <div className="row g-2">
            <div className="col-md-4">
              <input name="name" className="form-control" placeholder="Item name"
                value={form.name} onChange={handleChange} />
            </div>
            <div className="col-md-2">
              <select name="category" className="form-select" value={form.category} onChange={handleChange}>
                <option value="meals">Meals</option>
                <option value="beverages">Beverages</option>
                <option value="snacks">Snacks</option>
              </select>
            </div>
            <div className="col-md-2">
              <input name="price" className="form-control" placeholder="Price (EGP)"
                type="number" value={form.price} onChange={handleChange} />
            </div>
            <div className="col-md-2">
              <input name="stock_qty" className="form-control" placeholder="Stock qty"
                type="number" value={form.stock_qty} onChange={handleChange} />
            </div>
            <div className="col-md-2">
              <input name="max_order_qty" className="form-control" placeholder="Max order qty"
                type="number" value={form.max_order_qty} onChange={handleChange} />
            </div>
          </div>
          <div className="mt-2 form-check">
            <input type="checkbox" className="form-check-input" name="active"
              checked={form.active} onChange={handleChange} id="activeCheck" />
            <label className="form-check-label" htmlFor="activeCheck">Active (visible to students)</label>
          </div>
          <div className="mt-3">
            <button className="btn btn-success me-2" onClick={handleSubmit}>
              {editingId ? 'Save Changes' : 'Publish Item'}
            </button>
            {editingId && (
              <button className="btn btn-secondary" onClick={() => {
                setEditingId(null);
                setForm({ name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true });
              }}>Cancel Edit</button>
            )}
          </div>
        </div>
      </div>

      {/* Management Items Interactive Table */}
      <div className="table-responsive">
        <table className="table table-bordered table-hover align-middle">
          <thead className="table-dark">
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Category</th>
              <th>Price</th>
              <th>Stock</th>
              <th>Max Qty</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan="8" className="text-center text-muted py-3">No cafeteria menu data available.</td>
              </tr>
            ) : (
              items.map(item => (
                <tr key={item.id}>
                  <td className="text-muted small">{item.id}</td>
                  <td className="fw-bold">{item.name}</td>
                  <td><span className="badge bg-secondary text-capitalize">{item.category}</span></td>
                  <td>{item.price} EGP</td>
                  <td>{item.stock_qty}</td>
                  <td>{item.max_order_qty}</td>
                  <td>
                    <span className={`badge ${item.active ? 'bg-success' : 'bg-danger'}`}>
                      {item.active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-sm btn-primary me-1" onClick={() => handleEdit(item)}>Edit</button>
                    <button className="btn btn-sm btn-outline-danger" onClick={() => handleDelete(item.id)}>Deactivate</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}