import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://127.0.0.1:5001';

export default function AdminPanel() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({
    name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true
  });
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState('');

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    const res = await axios.get(`${API}/api/menu`);
    setItems(res.data);
  };

  const handleChange = e => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm({ ...form, [e.target.name]: val });
  };

  // FR18 — Create or Update
  const handleSubmit = async () => {
    try {
      if (editingId) {
        await axios.put(`${API}/api/admin/menu/${editingId}`, form);
        setMessage('Item updated successfully!');
      } else {
        await axios.post(`${API}/api/admin/menu`, form);
        setMessage('Item created successfully!');
      }
      setForm({ name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true });
      setEditingId(null);
      fetchItems();
    } catch (err) {
      setMessage('Error saving item.');
    }
  };

  // FR18 — Edit
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

  // FR18 — Soft delete
  const handleDelete = async (id) => {
    if (!window.confirm('Deactivate this item?')) return;
    await axios.delete(`${API}/api/admin/menu/${id}`);
    setMessage('Item deactivated.');
    fetchItems();
  };

  return (
    <div className="container mt-4">
      <h2>⚙️ Admin — Menu Management</h2>
      <p className="text-muted">FR18, FR19, FR52 — Create, update, deactivate menu items and set stock/quantity caps</p>

      {message && <div className="alert alert-info">{message}</div>}

      {/* Form */}
      <div className="card mb-4">
        <div className="card-header">{editingId ? 'Edit Item' : 'Add New Item'}</div>
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
              {editingId ? 'Update Item' : 'Add Item'}
            </button>
            {editingId && (
              <button className="btn btn-secondary" onClick={() => {
                setEditingId(null);
                setForm({ name: '', category: 'meals', price: '', stock_qty: '', max_order_qty: 10, active: true });
              }}>Cancel</button>
            )}
          </div>
        </div>
      </div>

      {/* Items Table */}
      <table className="table table-bordered table-hover">
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
          {items.map(item => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td>{item.name}</td>
              <td>{item.category}</td>
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
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Deactivate</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}