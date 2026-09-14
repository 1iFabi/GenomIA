import React from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';

const formatPercentage = (value) => {
  const number = Number(value) || 0;
  return Number.isInteger(number) ? `${number}` : number.toFixed(2).replace(/\.0+$/, '');
};

const IndigenousChartTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) {
    return null;
  }

  const item = payload[0].payload;

  return (
    <div className="indigenous-chart-tooltip">
      <strong>{item.label}</strong>
      <div>Porcentaje: <b>{formatPercentage(item.value)}%</b></div>
      <div>Variantes: {item.variant_count}</div>
      <div>Frec. alélica: {(item.avg_allele_frequency * 100).toFixed(2)}%</div>
    </div>
  );
};

const IndigenousBarChart = ({ data, height, onItemHover, onItemLeave }) => {
  const handleBarMouseEnter = (entry, index) => {
    const item = data[index] || entry;

    if (item) {
      onItemHover?.(item);
    }
  };

  return (
    <div
      className="indigenous-bar-chart"
      role="img"
      aria-label="Distribución porcentual de pueblos indígenas de Chile"
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 12, right: 42, bottom: 24, left: 8 }}
          barCategoryGap="24%"
        >
          <CartesianGrid horizontal={false} stroke="#e2e8f0" strokeDasharray="4 4" />
          <XAxis
            type="number"
            dataKey="value"
            domain={[0, 100]}
            ticks={[0, 20, 40, 60, 80, 100]}
            allowDecimals={false}
            tickFormatter={(value) => `${value}%`}
            tick={{ fill: '#64748b', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: '#cbd5e1' }}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={118}
            tick={{ fill: '#334155', fontSize: 13, fontWeight: 600 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: 'rgba(37, 99, 235, 0.08)' }}
            content={<IndigenousChartTooltip />}
            wrapperStyle={{ outline: 'none' }}
          />
          <Bar
            dataKey="value"
            name="Porcentaje"
            fill="#2563eb"
            background={{ fill: '#e8eef5' }}
            radius={[0, 7, 7, 0]}
            onMouseEnter={handleBarMouseEnter}
            onMouseLeave={onItemLeave}
          >
            {data.map((item) => (
              <Cell key={item.label} fill={item.color} />
            ))}
            <LabelList
              dataKey="value"
              position="right"
              formatter={(value) => `${formatPercentage(value)}%`}
              fill="#1e293b"
              fontSize={12}
              fontWeight={700}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default IndigenousBarChart;
