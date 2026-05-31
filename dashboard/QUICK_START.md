# React Dashboard - Quick Start

## Prerequisites
- Node.js 18+ (comes with npm 9+)
- Bifrost backend running on `http://localhost:8100`

## Setup

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Development Server
```bash
npm run dev
```

Server runs at: **http://localhost:5173**

Hot Module Replacement (HMR) enabled — changes auto-refresh.

### 3. View in Browser
Open http://localhost:5173 and you'll see:
- Dashboard with proposal list
- Filter buttons (All/Pending/Approved)
- Proposal cards with metrics summaries
- Click any proposal to see details and vote

## Project Structure

```
src/
├── pages/              # Full-page components
│   ├── DashboardPage   # Proposal list + filters
│   ├── ApprovalPage    # Proposal detail + voting
│   └── DeploymentMonitor  # Real-time deployment tracking
├── components/         # Reusable UI components
│   ├── Navbar          # Top navigation
│   └── ProposalList    # Proposal cards
├── hooks/              # React custom hooks
│   ├── useProposals    # Fetch proposals
│   ├── useVote         # Submit votes
│   └── useDeployment   # WebSocket deployment stream
├── api/                # API client
│   └── client.ts       # REST/WS endpoints
├── types/              # TypeScript interfaces
│   └── index.ts        # All type definitions
└── App.tsx             # Router configuration
```

## Common Commands

```bash
# Development
npm run dev

# Production build
npm run build

# Preview production bundle
npm run preview

# Type checking
npx tsc --noEmit

# Linting
npm run lint
```

## API Configuration

The dashboard expects Bifrost backend at `http://localhost:8100`.

To change this, set `VITE_API_URL` environment variable:

```bash
VITE_API_URL=http://staging-bifrost:8100 npm run dev
```

## Debugging

### Browser DevTools
- Open DevTools → Console to see API calls
- Network tab shows all REST and WebSocket connections
- React DevTools extension recommended

### TypeScript Errors
All TypeScript errors must be fixed before build:
```bash
npm run build
```

### API Connection Issues
1. Check Bifrost is running: `curl http://localhost:8100/health`
2. Check CORS headers if cross-origin: Bifrost should send `Access-Control-Allow-Origin: *`
3. WebSocket might need same-origin or explicit proxy

## Proposal Data Flow

```
Dashboard
  ↓ useProposals hook
  ↓ GET /api/v1/rl/proposals/pending
  ↓ ProposalList component renders
  ↓ User clicks proposal
  ↓ ApprovalPage loads
  ↓ GET /api/v1/rl/proposals/{id}
  ↓ Shows metrics + voting panel
  ↓ User votes (Odin/Frigg)
  ↓ POST /api/v1/rl/proposals/vote
  ↓ On success, proposal status updates
  ↓ Optional: navigate to /monitor for deployment tracking
  ↓ WS /api/v1/rl/deployments/live?proposal_id={id}
  ↓ Real-time deployment status streamed
```

## Styling

Uses **Tailwind CSS** (utility-first, no component library).

To customize:
- Edit `tailwind.config.ts` for colors, fonts, spacing
- Use inline `className="..."` in components
- Tailwind classes auto-complete in VSCode with official extension

## Building for Production

```bash
npm run build
```

Output goes to `dist/` folder. Static files ready to:
- Deploy to Vercel/Netlify
- Serve from nginx/Apache
- Embed in Electron app

**Build size**: ~70KB gzipped
**Chunks**: 1 main bundle (no code splitting yet)

---

**Next Steps**: Connect to Bifrost backend and test proposal workflows!
