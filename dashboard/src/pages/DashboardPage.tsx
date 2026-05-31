import { useState, useRef, useEffect } from 'react';
import { rlApi } from '../api/client';
import { ChatMessageRenderer } from '../components/ChatMessageRenderer';
import type { MessageContent } from '../components/ChatMessageRenderer';

const SAMPLE_AGENTS = [
  { id: 13, name: 'Mimir', emoji: '📚', desc: 'Knowledge & RAG' },
  { id: 14, name: 'Tyr', emoji: '⚖️', desc: 'Security & SIEM' },
  { id: 15, name: 'Syn', emoji: '👁️', desc: 'OCR & Vision' },
  { id: 16, name: 'Eir', emoji: '🏥', desc: 'Medical Expert' },
  { id: 17, name: 'Yggdrasil', emoji: '🌳', desc: 'Auth Gateway' },
  { id: 18, name: 'Heimdall', emoji: '🚪', desc: 'LLM Router' },
];

export interface ChatMessage {
  id: string;
  role: 'user' | 'odin' | 'agent';
  content: string | MessageContent;
  timestamp: string;
  status?: 'sending' | 'sent' | 'error';
  agent?: string;
  metadata?: Record<string, any>;
}


export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<'chat' | 'dashboard'>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'odin',
      content: '🏥 Halló! I am Odin, the All-Father of Asgard. I command and oversee all divine agents. Ask me to control any agent in the asgard_platform tenant, run diagnostics, or get status updates. What do you need?',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
      status: 'sending',
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await rlApi.chatWithOdin(input);

      const odinMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'odin',
        content: response.reply,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [
        ...prev.map((m) =>
          m.id === userMessage.id ? { ...m, status: 'sent' as const } : m
        ),
        odinMessage,
      ]);
    } catch (error) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === userMessage.id ? { ...m, status: 'error' as const } : m
        )
      );
      console.error('Failed to send message:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#f9fafb' }}>
      {/* Header */}
      <header style={{
        background: 'white',
        borderBottom: '1px solid #e5e7eb',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        padding: '16px 24px'
      }}>
        <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#1f2937', margin: 0 }}>🏛️ Odin</h1>
            <p style={{ fontSize: '13px', color: '#6b7280', margin: '4px 0 0 0' }}>Agent Command Center • asgard_platform</p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setActiveTab('chat')}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: 'none',
                fontWeight: '500',
                cursor: 'pointer',
                background: activeTab === 'chat' ? '#10b981' : '#f3f4f6',
                color: activeTab === 'chat' ? 'white' : '#1f2937',
                transition: 'all 0.2s'
              }}
            >
              💬 Chat
            </button>
            <button
              onClick={() => setActiveTab('dashboard')}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: 'none',
                fontWeight: '500',
                cursor: 'pointer',
                background: activeTab === 'dashboard' ? '#10b981' : '#f3f4f6',
                color: activeTab === 'dashboard' ? 'white' : '#1f2937',
                transition: 'all 0.2s'
              }}
            >
              📊 Dashboard
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {activeTab === 'chat' && (
          <>
            {/* Chat Messages */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              {messages.map((message) => (
                <div
                  key={message.id}
                  style={{
                    display: 'flex',
                    justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start'
                  }}
                >
                  <div
                    style={{
                      maxWidth: '70%',
                      padding: '12px 16px',
                      borderRadius: '8px',
                      background: message.role === 'user'
                        ? '#10b981'
                        : message.role === 'agent'
                        ? '#ecfdf5'
                        : 'white',
                      color: message.role === 'user'
                        ? 'white'
                        : message.role === 'agent'
                        ? '#065f46'
                        : '#1f2937',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                      border: message.role === 'agent' ? '1px solid #d1fae5' : 'none'
                    }}
                  >
                    {message.agent && (
                      <p style={{ fontSize: '11px', fontWeight: '600', margin: '0 0 8px 0', opacity: 0.8 }}>
                        {message.agent}
                      </p>
                    )}
                    <ChatMessageRenderer content={message.content} />
                    {message.status === 'sending' && (
                      <p style={{ fontSize: '11px', margin: '8px 0 0 0', opacity: 0.7 }}>⏳ Sending...</p>
                    )}
                    {message.status === 'error' && (
                      <p style={{ fontSize: '11px', margin: '8px 0 0 0', color: '#dc2626' }}>❌ Failed</p>
                    )}
                    <p style={{ fontSize: '11px', margin: '8px 0 0 0', opacity: 0.6 }}>
                      {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Chat Input */}
            <div style={{
              background: 'white',
              borderTop: '1px solid #e5e7eb',
              padding: '16px 24px'
            }}>
              <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask Odin... 'list agents', 'agent status', 'help'"
                  disabled={loading}
                  style={{
                    flex: 1,
                    padding: '10px 14px',
                    border: '1px solid #e5e7eb',
                    borderRadius: '6px',
                    fontSize: '14px',
                    fontFamily: 'inherit',
                    color: '#1f2937',
                    outline: 'none',
                    transition: 'border-color 0.2s',
                    opacity: loading ? 0.6 : 1
                  }}
                  onFocus={(e) => e.currentTarget.style.borderColor = '#10b981'}
                  onBlur={(e) => e.currentTarget.style.borderColor = '#e5e7eb'}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  style={{
                    padding: '10px 20px',
                    borderRadius: '6px',
                    border: 'none',
                    background: loading || !input.trim() ? '#d1d5db' : '#10b981',
                    color: 'white',
                    fontWeight: '500',
                    cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                    transition: 'background 0.2s'
                  }}
                >
                  {loading ? '⏳' : '→'}
                </button>
              </form>
            </div>
          </>
        )}

        {activeTab === 'dashboard' && (
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px'
          }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
              <h2 style={{ fontSize: '18px', fontWeight: '600', color: '#1f2937', marginBottom: '16px' }}>
                🏛️ Divine Agents
              </h2>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '16px'
              }}>
                {SAMPLE_AGENTS.map((agent) => (
                  <div
                    key={agent.id}
                    style={{
                      background: 'white',
                      borderRadius: '8px',
                      padding: '20px',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                      border: '1px solid #e5e7eb',
                      transition: 'all 0.2s',
                      cursor: 'pointer'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.boxShadow = '0 10px 15px rgba(16,185,129,0.15)';
                      e.currentTarget.style.borderColor = '#10b981';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
                      e.currentTarget.style.borderColor = '#e5e7eb';
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                      <div>
                        <div style={{ fontSize: '28px', marginBottom: '4px' }}>{agent.emoji}</div>
                        <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#1f2937', margin: 0 }}>{agent.name}</h3>
                        <p style={{ fontSize: '12px', color: '#6b7280', margin: '4px 0 0 0' }}>{agent.desc}</p>
                      </div>
                      <span style={{
                        display: 'inline-block',
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: '#10b981'
                      }} />
                    </div>
                    <button style={{
                      width: '100%',
                      padding: '10px',
                      marginTop: '12px',
                      borderRadius: '6px',
                      border: '1px solid #10b981',
                      background: '#f0fdf4',
                      color: '#10b981',
                      fontWeight: '500',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#10b981';
                      e.currentTarget.style.color = 'white';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = '#f0fdf4';
                      e.currentTarget.style.color = '#10b981';
                    }}
                    >
                      Run Agent
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
