import { useNavigate } from 'react-router-dom';

export default function Navbar() {
  const navigate = useNavigate();

  return (
    <nav className="bg-white shadow">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          <div
            onClick={() => navigate('/')}
            className="text-2xl font-bold text-blue-600 cursor-pointer"
          >
            🏥 Asgard
          </div>
          <div className="text-sm text-gray-600">
            Agent Reinforcement Learning Governance
          </div>
        </div>
      </div>
    </nav>
  );
}
