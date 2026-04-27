// @ts-nocheck
'use client';

import { useMemo, useState } from 'react';

const CATEGORY_COLOR = {
  goodStrong: '#1f8f3a',
  goodSoft: '#74b816',
  good: '#2f9e44',
  warning: '#f59f00',
  bad: '#e03131',
  badStrong: '#9d0208',
  uncertain: '#868e96',
  other: '#4c6ef5',
  blank: '#495057',
};

function percent(value: number) {
  if (!Number.isFinite(value)) return '0.0%';
  return `${(value * 100).toFixed(1)}%`;
}

function count(value: number) {
  return Number(value || 0).toLocaleString('en-US');
}

function shortDate(value: string) {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

function colorFor(item) {
  return CATEGORY_COLOR[item.tone] || CATEGORY_COLOR[item.category] || CATEGORY_COLOR.other;
}

function StackedBar({ breakdown }) {
  const rows = (breakdown || []).filter((item) => item.count > 0);
  if (!rows.length) return <div className="analyticsEmptyBar" />;
  return (
    <div className="analyticsStackedBar" aria-hidden="true">
      {rows.map((item) => (
        <div
          key={`${item.answer}:${item.category}`}
          className="analyticsStackedSegment"
          style={{
            width: `${Math.max(item.ratio * 100, 0.6)}%`,
            background: colorFor(item),
          }}
          title={`${item.answer}: ${count(item.count)} (${percent(item.ratio)})`}
        />
      ))}
    </div>
  );
}

function Metric({ label, value, hint }) {
  return (
    <div className="analyticsMetric">
      <div className="analyticsMetricLabel">{label}</div>
      <div className="analyticsMetricValue">{value}</div>
      {hint ? <div className="analyticsMetricHint">{hint}</div> : null}
    </div>
  );
}

function MiniBar({ value, tone = 'blue' }) {
  return (
    <div className="miniBar">
      <div className={`miniBarFill is-${tone}`} style={{ width: `${Math.min(Math.max(value * 100, 0), 100)}%` }} />
    </div>
  );
}

export default function AdminAnalyticsDashboard({ analytics }) {
  const users = analytics?.users || [];
  const [selectedReviewerId, setSelectedReviewerId] = useState('ALL');

  const selectedUser = useMemo(
    () => users.find((user) => user.reviewerId === selectedReviewerId) || null,
    [selectedReviewerId, users],
  );

  const visibleQuestionStats = selectedUser?.questionStats || analytics?.questionOverall || [];
  const visibleTreeQuestionStats = selectedUser?.treeQuestionStats || analytics?.treeQuestionOverall || [];
  const completeUsers = users.filter((user) => user.targetNodes > 0 && user.completionRate >= 1);
  const activeUsers = users.filter((user) => user.answeredNodes > 0);

  return (
    <main className="analyticsShell">
      <header className="analyticsHeader">
        <div>
          <div className="analyticsEyebrow">Admin only</div>
          <h1>Review Analytics</h1>
          <p>Live statistics from review_annotations, assignments, and image manifest.</p>
        </div>
        <div className="analyticsHeaderActions">
          <a className="secondaryButton" href="/">Review tool</a>
          <button
            className="secondaryButton"
            type="button"
            onClick={async () => {
              await fetch('/api/auth/logout', { method: 'POST' }).catch(() => null);
              window.location.href = '/login';
            }}
          >
            Logout
          </button>
        </div>
      </header>

      <section className="analyticsMetricsGrid">
        <Metric label="Users present" value={`${analytics.summary.presentUsers} / 20`} hint={`${analytics.summary.assignedUsers} assigned`} />
        <Metric label="Completed users" value={`${completeUsers.length}`} hint={`${activeUsers.length} active users`} />
        <Metric label="Node completion" value={percent(analytics.summary.completionRate)} hint={`${count(analytics.summary.totalAnsweredNodes)} / ${count(analytics.summary.totalTargetNodes)}`} />
        <Metric label="Bad node rate" value={percent(analytics.summary.badRate)} hint={`${count(analytics.summary.totalBadNodes)} bad nodes`} />
        <Metric label="Nonideal rate" value={percent(analytics.summary.nonidealRate)} hint={`${count(analytics.summary.totalNonidealNodes)} nonideal nodes`} />
        <Metric label="Tree answers" value={count(analytics.summary.totalTreeAnswers)} hint={`${percent(analytics.summary.treeNonidealRate)} nonideal`} />
      </section>

      <section className="analyticsBand">
        <div className="analyticsSectionHeader">
          <div>
            <h2>User Progress</h2>
            <p>Completion and issue rates for user1 through user20.</p>
          </div>
          <select
            className="analyticsSelect"
            value={selectedReviewerId}
            onChange={(event) => setSelectedReviewerId(event.target.value)}
          >
            <option value="ALL">Overall question stats</option>
            {users.map((user) => (
              <option key={user.reviewerId} value={user.reviewerId}>
                {user.reviewerId}
              </option>
            ))}
          </select>
        </div>

        <div className="analyticsUserRows">
          {users.map((user) => (
            <button
              key={user.reviewerId}
              className={`analyticsUserRow ${selectedReviewerId === user.reviewerId ? 'isActive' : ''}`}
              onClick={() => setSelectedReviewerId(user.reviewerId)}
              type="button"
            >
              <div className="analyticsUserName">
                <strong>{user.reviewerId}</strong>
                <span>{user.present ? 'present' : 'missing'}</span>
              </div>
              <div className="analyticsUserBarCell">
                <MiniBar value={user.completionRate} tone={user.completionRate >= 1 ? 'green' : 'blue'} />
                <span>{percent(user.completionRate)}</span>
              </div>
              <div>{count(user.answeredNodes)} / {count(user.targetNodes)}</div>
              <div className="analyticsRate isBad">{percent(user.badRate)}</div>
              <div className="analyticsRate isNonideal">{percent(user.nonidealRate)}</div>
              <div>{count(user.treeSummariesAnswered)} tree answers</div>
              <div>{shortDate(user.lastUpdatedAt)}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="analyticsBand">
        <div className="analyticsSectionHeader">
          <div>
            <h2>{selectedUser ? `${selectedUser.reviewerId} Question Distribution` : 'Overall Question Distribution'}</h2>
            <p>Green shades are good, yellow is minor or acceptable, red shades are bad, gray is uncertain.</p>
          </div>
        </div>

        <div className="questionDistributionList">
          {visibleQuestionStats.map((question) => (
            <div className="questionDistributionRow" key={question.id}>
              <div className="questionDistributionMeta">
                <strong>{question.number}</strong>
                <span>{question.id}</span>
                <small>{question.title}</small>
              </div>
              <div className="questionDistributionChart">
                <StackedBar breakdown={question.breakdown} />
                <div className="questionLegendLine">
                  {(question.breakdown || []).slice(0, 5).map((item) => (
                    <span key={item.answer}>
                      <i style={{ background: colorFor(item) }} />
                      {item.answer || '-'} {count(item.count)} ({percent(item.ratio)})
                    </span>
                  ))}
                </div>
              </div>
              <div className="questionDistributionCount">
                {count(question.total ?? question.answered)}
                {selectedUser ? <small>{percent(question.answeredNodeCoverage)} of answered nodes</small> : <small>responses</small>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="analyticsBand">
        <div className="analyticsSectionHeader">
          <div>
            <h2>{selectedUser ? `${selectedUser.reviewerId} Tree Summary Questions` : 'Overall Tree Summary Questions'}</h2>
            <p>Whole-tree answers from each image&apos;s tree_summary block. Legacy node questions are excluded.</p>
          </div>
        </div>

        <div className="questionDistributionList">
          {visibleTreeQuestionStats.length ? visibleTreeQuestionStats.map((question) => (
            <div className="questionDistributionRow" key={question.id}>
              <div className="questionDistributionMeta">
                <strong>{question.number}</strong>
                <span>{question.id}</span>
                <small>{question.title}</small>
              </div>
              <div className="questionDistributionChart">
                <StackedBar breakdown={question.breakdown} />
                <div className="questionLegendLine">
                  {(question.breakdown || []).slice(0, 5).map((item) => (
                    <span key={item.answer}>
                      <i style={{ background: colorFor(item) }} />
                      {item.answer || '-'} {count(item.count)} ({percent(item.ratio)})
                    </span>
                  ))}
                </div>
              </div>
              <div className="questionDistributionCount">
                {count(question.total ?? question.answered)}
                {selectedUser ? <small>{percent(question.imageCoverage)} of assigned images</small> : <small>tree answers</small>}
              </div>
            </div>
          )) : (
            <div className="analyticsEmptyNotice">No tree summary answers yet.</div>
          )}
        </div>
      </section>

      <div className="analyticsTwoColumn">
        <section className="analyticsBand">
          <div className="analyticsSectionHeader">
            <div>
              <h2>Leaf vs Non-Leaf</h2>
              <p>Overall response patterns by tree position.</p>
            </div>
          </div>
          <div className="leafGrid">
            {(analytics.questionOverall || []).slice(0, 7).map((question) => (
              <div className="leafRow" key={question.id}>
                <div>
                  <strong>{question.number}</strong>
                  <span>{question.id}</span>
                </div>
                <label>Leaf</label>
                <StackedBar breakdown={question.leafBreakdown} />
                <label>Non-leaf</label>
                <StackedBar breakdown={question.nonLeafBreakdown} />
              </div>
            ))}
          </div>
        </section>

        <section className="analyticsBand">
          <div className="analyticsSectionHeader">
            <div>
              <h2>Daily Flow</h2>
              <p>Total answered nodes per UTC date.</p>
            </div>
          </div>
          <div className="timelineList">
            {(analytics.timeline || [])
              .filter((item) => item.reviewerId === 'ALL')
              .map((item) => {
                const maxCount = Math.max(...(analytics.timeline || []).filter((row) => row.reviewerId === 'ALL').map((row) => row.count), 1);
                return (
                  <div className="timelineRow" key={item.date}>
                    <span>{item.date}</span>
                    <MiniBar value={item.count / maxCount} tone="green" />
                    <strong>{count(item.count)}</strong>
                  </div>
                );
              })}
          </div>
        </section>
      </div>

      <div className="analyticsTwoColumn">
        <section className="analyticsBand">
          <div className="analyticsSectionHeader">
            <div>
              <h2>Problem Labels</h2>
              <p>Labels with highest bad response rates, minimum 10 responses.</p>
            </div>
          </div>
          <div className="rankList">
            {(analytics.topLabels || []).map((row, index) => (
              <div className="rankRow" key={row.label}>
                <span>{index + 1}</span>
                <strong>{row.label}</strong>
                <MiniBar value={row.badRate} tone="red" />
                <em>{percent(row.badRate)}</em>
                <small>{count(row.responses)} responses</small>
              </div>
            ))}
          </div>
        </section>

        <section className="analyticsBand">
          <div className="analyticsSectionHeader">
            <div>
              <h2>Problem Images</h2>
              <p>Images with highest bad response rates, minimum 10 responses.</p>
            </div>
          </div>
          <div className="rankList">
            {(analytics.topImages || []).map((row, index) => (
              <div className="rankRow" key={row.imageId}>
                <span>{index + 1}</span>
                <strong>{row.imageId}</strong>
                <MiniBar value={row.badRate} tone="red" />
                <em>{percent(row.badRate)}</em>
                <small>{count(row.responses)} responses</small>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
