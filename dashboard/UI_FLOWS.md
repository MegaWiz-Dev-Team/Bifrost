# React Dashboard - UI Flows & Screens

## Dashboard Overview

### Screen 1: Main Dashboard (/)
```
┌─────────────────────────────────────────────────────────────┐
│  🏥 Asgard  |  Agent Reinforcement Learning Governance       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  🏥 Agent Improvement Proposals                              │
│                                                               │
│  [All (5)]  [Pending (3)]  [Approved (2)]                   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Agent: eir-sleep                                     │ ← clickable │
│  │ Proposal ID: prop_12345                              │    │
│  │ [PENDING]                                            │    │
│  │                                                       │    │
│  │ Quality: 0.92 (from 0.88) │ Relevance: 0.87         │    │
│  │ Latency: 245ms (from 280) │ Confidence: 0.91        │    │
│  │ Created 2026-05-28                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Agent: eir-cardio                                    │    │
│  │ Proposal ID: prop_12346                              │    │
│  │ [PENDING]                                            │    │
│  │                                                       │    │
│  │ Quality: 0.95 (from 0.90) │ Relevance: 0.92         │    │
│  │ Latency: 198ms (from 220) │ Confidence: 0.94        │    │
│  │ Created 2026-05-28                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Agent: eir                                           │    │
│  │ Proposal ID: prop_12347                              │    │
│  │ [APPROVED]                                           │    │
│  │                                                       │    │
│  │ Quality: 0.91 (from 0.86) │ Relevance: 0.89         │    │
│  │ Latency: 212ms (from 250) │ Confidence: 0.88        │    │
│  │ Created 2026-05-27                                   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Filter by status: All / Pending / Approved
- Each card shows 4 key metrics (Quality, Relevance, Latency, Confidence)
- Color badges: Yellow (Pending) | Green (Approved) | Red (Rejected)
- Click any proposal → navigate to approval page
- Count display: "All (5)" shows total proposals

---

### Screen 2: Proposal Approval (/proposals/:proposalId)
```
┌─────────────────────────────────────────────────────────────┐
│  🏥 Asgard  |  Agent Reinforcement Learning Governance       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ← Back to proposals                                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Agent: eir-sleep                                    │    │
│  │ Proposal ID: prop_12345                             │    │
│  │                                                      │    │
│  │ 📊 Proposed Improvements                            │    │
│  │                                                      │    │
│  │ ┌──────────────┐  ┌──────────────┐                 │    │
│  │ │Quality Score │  │Relevance Score│                 │    │
│  │ │0.88 → 0.92   │  │0.85 → 0.87    │                 │    │
│  │ │✅ +4.5%      │  │✅ +2.4%       │                 │    │
│  │ └──────────────┘  └──────────────┘                 │    │
│  │                                                      │    │
│  │ ┌──────────────┐  ┌──────────────┐                 │    │
│  │ │Latency (ms)  │  │Confidence    │                 │    │
│  │ │280 → 245     │  │0.89 → 0.91    │                 │    │
│  │ │✅ -12.5%     │  │✅ +2.2%       │                 │    │
│  │ └──────────────┘  └──────────────┘                 │    │
│  │                                                      │    │
│  │ 🗳️ Approval Voting                                 │    │
│  │                                                      │    │
│  │ ┌─────────────────────────────────────────────┐    │    │
│  │ │ Odin                                    ⏳     │ ← pending
│  │ │ Pending                                     │    │    │
│  │ └─────────────────────────────────────────────┘    │    │
│  │                                                      │    │
│  │ ┌─────────────────────────────────────────────┐    │    │
│  │ │ Frigg                                   ⏳     │ ← pending │
│  │ │ Pending        [✅ Approve] [❌ Reject]     │    │    │
│  │ └─────────────────────────────────────────────┘    │    │
│  │                                                      │    │
│  │ ┌─────────────────────────────────────────────┐    │    │
│  │ │ ⏳ Waiting for approval from Odin...       │    │    │
│  │ └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Shows proposal details with agent ID
- 4 metric cards: before → after with % change
- ✅ Green for improvements, ❌ Red for regressions
- Voting panel: One card per voter (Odin/Frigg)
- Vote buttons: Approve (green) | Reject (red)
- Disabled after voting (prevents duplicate votes)
- Status message: Shows consensus requirement
- Back button returns to dashboard

---

### Screen 3: Deployment Monitor (/proposals/:proposalId/monitor)
```
┌─────────────────────────────────────────────────────────────┐
│  🏥 Asgard  |  Agent Reinforcement Learning Governance       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ← Back to proposals                                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 🚀 Deployment Monitor                              │    │
│  │ Proposal: prop_12345                               │    │
│  │                                                      │    │
│  │ ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │    │
│  │ │Current Phase │  │Deployment %  │  │Overall %  │ │    │
│  │ │STAGED_50     │  │50%           │  │52%        │ │    │
│  │ └──────────────┘  └──────────────┘  └───────────┘ │    │
│  │                                                      │    │
│  │ Phase Timeline:                                     │    │
│  │                                                      │    │
│  │ ✅ Canary (5%)                                     │    │
│  │ ⚙️ Staged 25%                                      │    │
│  │ ⚙️ Staged 50%      [ACTIVE]                        │    │
│  │ ⏳ Full Rollout (100%)                             │    │
│  │                                                      │    │
│  │ Live Metrics:                                       │    │
│  │                                                      │    │
│  │ ┌──────────────┐  ┌──────────────┐                │    │
│  │ │Quality Score │  │Latency (ms)  │                │    │
│  │ │0.92          │  │248           │                │    │
│  │ └──────────────┘  └──────────────┘                │    │
│  │                                                      │    │
│  │ ┌──────────────┐  ┌──────────────┐                │    │
│  │ │Error Rate    │  │Status        │                │    │
│  │ │0.02%         │  │⚙️ in_progress│                │    │
│  │ └──────────────┘  └──────────────┘                │    │
│  │                                                      │    │
│  │ ✅ Deployment is healthy and proceeding normally   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Shows current deployment phase (Canary → Staged-25 → Staged-50 → Full)
- Real-time metrics from WebSocket
- Phase timeline with status indicators:
  - ✅ Complete (green)
  - ⚙️ Active (blue, animated)
  - ⏳ Upcoming (gray)
- Live metric cards: Quality, Latency, Error Rate, Status
- Health status display
- Auto-refresh via WebSocket stream
- Rollback detection with reason display

---

## User Interaction Flows

### Flow 1: Browse & Filter Proposals
```
User visits /
  ↓ sees all proposals
  ↓ clicks [Pending] filter button
  ↓ list updates (no page reload)
  ↓ sees only pending proposals
```

### Flow 2: Vote on Proposal (Odin)
```
User clicks proposal card
  ↓ navigates to /proposals/{id}
  ↓ sees proposal details + metrics
  ↓ scrolls to voting panel
  ↓ clicks [Approve] as Odin
  ↓ API call: POST /proposals/vote
  ↓ vote button disables
  ↓ status message updates
  ↓ waits for Frigg approval
```

### Flow 3: Both Vote & Deployment Begins
```
Odin voted approve
  ↓ Frigg votes approve
  ↓ Backend initiates deployment
  ↓ User sees deployment status updating
  ↓ Proposal status changes to "deployed"
  ↓ User can navigate to monitor page
```

### Flow 4: Monitor Live Deployment
```
User navigates to /proposals/{id}/monitor
  ↓ WebSocket connects to backend
  ↓ current phase: "canary" (5%)
  ↓ backend progresses through phases
  ↓ real-time metrics stream in
  ↓ phase indicator updates (Upcoming → Active → Complete)
  ↓ final phase: Full (100%)
  ↓ deployment completes ✅
```

---

## Component Hierarchy

```
App
├── Router (React Router v6)
│   ├── Navbar
│   │   └── Logo (clickable → home)
│   └── Routes
│       ├── Route: "/" 
│       │   └── DashboardPage
│       │       ├── useProposals hook
│       │       ├── Filter buttons (status)
│       │       └── ProposalList
│       │           └── [Proposal Card] × N
│       │
│       ├── Route: "/proposals/:id"
│       │   └── ApprovalPage
│       │       ├── useProposal (fetch details)
│       │       ├── useVote hook
│       │       ├── MetricCard × 4
│       │       ├── VoteCard × 2 (Odin, Frigg)
│       │       └── Status Message
│       │
│       └── Route: "/proposals/:id/monitor"
│           └── DeploymentMonitorPage
│               ├── useDeployment (WebSocket)
│               ├── Phase Timeline
│               │   └── PhaseIndicator × 4
│               ├── Live Metrics Cards × 4
│               └── Status Message
```

---

## Color Scheme

| Element | Color | RGB | Usage |
|---------|-------|-----|-------|
| Primary | Blue | #3B82F6 | Links, buttons, accent |
| Success | Green | #16A34A | Improvements, approved votes |
| Error | Red | #DC2626 | Failures, rejected votes |
| Warning | Amber | #FBBF24 | Pending status |
| Background | Light Gray | #F3F4F6 | Page background |
| Card | White | #FFFFFF | Content containers |
| Border | Gray | #E5E7EB | Dividers, outlines |
| Text Primary | Gray-900 | #111827 | Main text |
| Text Secondary | Gray-600 | #4B5563 | Helper text |

---

## Responsive Design

- **Desktop** (1024px+): Full layout with 4-column grids
- **Tablet** (768px): 2-column grids, adjusted margins
- **Mobile** (< 768px): Single column, full-width cards

All components use Tailwind CSS breakpoints for responsive scaling.

---

## Accessibility

- Semantic HTML (`<button>`, `<nav>`, `<section>`)
- Keyboard navigation supported (Tab to focus, Enter to activate)
- Color not sole indicator (icons: ✅, ❌, ⚙️, etc.)
- ARIA labels on interactive elements
- Focus states visible on buttons

---

## Performance

- **Bundle Size**: 70KB gzipped (React + Router + CSS)
- **Time to Interactive**: <2 seconds (Vite optimized)
- **WebSocket**: Lazy-loaded on monitor page only
- **API Calls**: Minimal (GET proposals, POST vote, WS stream)
- **Re-renders**: Only when data changes (React hooks optimize)

---

## State Management

Simple and explicit:
- Local component state: `useState` for form inputs
- Server state: API hooks (`useProposals`, `useVote`, `useDeployment`)
- No Redux/Context needed (small app scope)
- WebSocket connection auto-managed by hook cleanup

---

**Generated**: 2026-05-28  
**Phase**: B (React Frontend) ✅ Complete
