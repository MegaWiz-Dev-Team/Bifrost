import React from 'react';
import {
  LineChart,
  BarChart,
  PieChart,
  Line,
  Bar,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export interface TableData {
  type: 'table';
  headers: string[];
  rows: (string | number | null)[][];
}

export interface ChartData {
  type: 'chart';
  chartType: 'line' | 'bar' | 'pie';
  title?: string;
  data: Record<string, any>[];
  dataKey?: string;
  nameKey?: string;
}

export interface MessageContent {
  text: string;
  tables?: TableData[];
  charts?: ChartData[];
}

interface ChatMessageRendererProps {
  content: MessageContent | string;
}

const CHART_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

const TableRenderer: React.FC<TableData> = ({ headers, rows }) => (
  <div style={{ overflowX: 'auto', marginTop: '12px' }}>
    <table style={{
      width: '100%',
      borderCollapse: 'collapse',
      borderRadius: '6px',
      overflow: 'hidden',
      fontSize: '13px'
    }}>
      <thead>
        <tr style={{ background: '#f0fdf4' }}>
          {headers.map((header, i) => (
            <th
              key={i}
              style={{
                padding: '10px 12px',
                textAlign: 'left',
                fontWeight: '600',
                color: '#065f46',
                borderBottom: '2px solid #d1fae5'
              }}
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIdx) => (
          <tr key={rowIdx} style={{ borderBottom: '1px solid #d1fae5' }}>
            {row.map((cell, cellIdx) => (
              <td
                key={cellIdx}
                style={{
                  padding: '10px 12px',
                  color: '#065f46'
                }}
              >
                {cell === null ? '-' : cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ChartRenderer: React.FC<ChartData> = ({
  chartType,
  title,
  data,
  dataKey = 'value',
  nameKey = 'name',
}) => {
  if (data.length === 0) return null;

  const commonProps = {
    data,
    margin: { top: 5, right: 30, left: 0, bottom: 5 },
  };

  return (
    <div style={{ marginTop: '12px', width: '100%' }}>
      {title && <p style={{ fontSize: '13px', fontWeight: '600', color: '#065f46', marginBottom: '8px' }}>{title}</p>}
      <ResponsiveContainer width="100%" height={300}>
        {chartType === 'line' && (
          <LineChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d1fae5" />
            <XAxis dataKey={nameKey} stroke="#10b981" />
            <YAxis stroke="#10b981" />
            <Tooltip
              contentStyle={{ backgroundColor: '#f0fdf4', border: '1px solid #d1fae5' }}
              labelStyle={{ color: '#065f46' }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke={CHART_COLORS[0]}
              strokeWidth={2}
              dot={{ fill: CHART_COLORS[0], r: 4 }}
            />
          </LineChart>
        )}
        {chartType === 'bar' && (
          <BarChart {...commonProps}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d1fae5" />
            <XAxis dataKey={nameKey} stroke="#10b981" />
            <YAxis stroke="#10b981" />
            <Tooltip
              contentStyle={{ backgroundColor: '#f0fdf4', border: '1px solid #d1fae5' }}
              labelStyle={{ color: '#065f46' }}
            />
            <Legend />
            <Bar dataKey={dataKey} fill={CHART_COLORS[0]} radius={[8, 8, 0, 0]} />
          </BarChart>
        )}
        {chartType === 'pie' && (
          <PieChart>
            <Pie
              data={data}
              dataKey={dataKey}
              nameKey={nameKey}
              cx="50%"
              cy="50%"
              outerRadius={80}
              label
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: '#f0fdf4', border: '1px solid #d1fae5' }}
              labelStyle={{ color: '#065f46' }}
            />
          </PieChart>
        )}
      </ResponsiveContainer>
    </div>
  );
};

export const ChatMessageRenderer: React.FC<ChatMessageRendererProps> = ({ content }) => {
  if (typeof content === 'string') {
    return <p style={{ fontSize: '13px', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>{content}</p>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <p style={{ fontSize: '13px', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>{content.text}</p>
      {content.tables?.map((table, idx) => (
        <TableRenderer key={`table-${idx}`} {...table} />
      ))}
      {content.charts?.map((chart, idx) => (
        <ChartRenderer key={`chart-${idx}`} {...chart} />
      ))}
    </div>
  );
};
