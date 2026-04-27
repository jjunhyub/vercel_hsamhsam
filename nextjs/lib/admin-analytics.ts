// @ts-nocheck

import { getAssignmentsTableName, getManifestTableName, getReviewTableName, getSupabaseAdmin } from './supabase/admin';
import { chunk, humanLabel } from './utils';

const REVIEWER_MIN = 1;
const REVIEWER_MAX = 20;

const QUESTION_DEFS = [
  { id: 'label', number: 'Q1', title: 'Label exists' },
  { id: 'mask_missing', number: 'Q2', title: 'Missing area' },
  { id: 'mask_extra', number: 'Q3', title: 'Extra area' },
  { id: 'instance', number: 'Q4', title: 'Instance separation' },
  { id: 'mask_quality', number: 'Q5', title: 'Mask quality' },
  { id: 'decomposition', number: 'Q6', title: 'Decomposition' },
  { id: 'missing_child', number: 'Q7', title: 'Missing child' },
];

const TREE_QUESTION_DEFS = [
  { id: 'overall_consistency', number: 'T1', title: 'Overall tree consistency' },
  { id: 'missing_critical_nodes', number: 'T2', title: 'Missing critical nodes' },
  { id: 'ontology_fit', number: 'T3', title: 'Ontology fit' },
  { id: 'priority_fix', number: 'T4', title: 'Priority fix' },
];

const GOOD_BY_Q = {
  label: new Set(['\uC608', '\uB9DE\uC74C']),
  instance: new Set(['\uC815\uD655']),
  mask_extra: new Set(['\uD3EC\uD568\uD558\uC9C0 \uC54A\uC74C']),
  mask_missing: new Set(['\uBAA8\uB450 \uD3EC\uD568\uD568']),
  mask_quality: new Set(['\uC815\uD655']),
  decomposition: new Set(['\uC608', '\uC5C6\uC74C', '\uB9DE\uC74C']),
  missing_child: new Set(['\uC608', '\uC5C6\uC74C']),
  overall_consistency: new Set(['\uB9DE\uC74C', '\uB300\uCCB4\uB85C \uB9DE\uC74C']),
  missing_critical_nodes: new Set(['\uC5C6\uC74C']),
  ontology_fit: new Set(['\uC88B\uC74C', '\uB9E4\uC6B0 \uC88B\uC74C', '\uB9DE\uC74C']),
  priority_fix: new Set(['\uC5C6\uC74C']),
};

const WARNING_BY_Q = {
  label: new Set(['\uBD80\uBD84\uC801\uC73C\uB85C \uB9DE\uC74C']),
  instance: new Set(['\uC218\uC6A9 \uAC00\uB2A5']),
  mask_extra: new Set(['\uC57D\uAC04 \uD3EC\uD568']),
  mask_missing: new Set(['\uC57D\uAC04 \uB193\uCE68']),
  mask_quality: new Set(['\uC218\uC6A9 \uAC00\uB2A5']),
  decomposition: new Set(['\uC870\uAE08 \uC788\uC74C']),
  missing_child: new Set(['\uC870\uAE08 \uC788\uC74C']),
  overall_consistency: new Set(['\uBD80\uBD84\uC801\uC73C\uB85C \uB9DE\uC74C']),
  missing_critical_nodes: new Set(['\uC870\uAE08 \uC788\uC74C']),
  ontology_fit: new Set(['\uBCF4\uD1B5']),
  priority_fix: new Set(['\uC870\uAE08 \uC788\uC74C']),
};

const BAD_BY_Q = {
  label: new Set(['\uC544\uB2C8\uC624', '\uC544\uB2D8']),
  instance: new Set(['\uBD80\uC815\uD655', '\uC2E4\uD328']),
  mask_extra: new Set(['\uB9CE\uC774 \uD3EC\uD568']),
  mask_missing: new Set(['\uB9CE\uC774 \uB193\uCE68']),
  mask_quality: new Set(['\uBD80\uC815\uD655', '\uC2E4\uD328']),
  decomposition: new Set(['\uC544\uB2C8\uC624', '\uC544\uB2D8', '\uB9CE\uC774 \uC788\uC74C']),
  missing_child: new Set(['\uC544\uB2C8\uC624', '\uB9CE\uC774 \uC788\uC74C']),
  overall_consistency: new Set(['\uC544\uB2D8']),
  missing_critical_nodes: new Set(['\uB9CE\uC774 \uC788\uC74C']),
  ontology_fit: new Set(['\uB098\uC068', '\uC544\uB2D8']),
  priority_fix: new Set(['\uB9CE\uC774 \uC788\uC74C']),
};

const UNCERTAIN = new Set(['\uD310\uB2E8\uBD88\uAC00']);

function reviewerIds() {
  const ids = [];
  for (let i = REVIEWER_MIN; i <= REVIEWER_MAX; i += 1) ids.push(`user${i}`);
  return ids;
}

function isTargetReviewer(reviewerId: string) {
  return /^user\d+$/.test(String(reviewerId || '')) &&
    Number(String(reviewerId).replace('user', '')) >= REVIEWER_MIN &&
    Number(String(reviewerId).replace('user', '')) <= REVIEWER_MAX;
}

function normalizeAnswer(value: any) {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.join('|');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function hasAnswer(value: any) {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'string') return value.trim().length > 0;
  return true;
}

function categoryFor(questionId: string, answer: string) {
  if (GOOD_BY_Q[questionId]?.has(answer)) return 'good';
  if (WARNING_BY_Q[questionId]?.has(answer)) return 'warning';
  if (BAD_BY_Q[questionId]?.has(answer)) return 'bad';
  if (UNCERTAIN.has(answer)) return 'uncertain';
  return answer ? 'other' : 'blank';
}

function toneFor(questionId: string, answer: string, category: string) {
  if (questionId === 'overall_consistency') {
    if (answer === '\uB9DE\uC74C') return 'goodStrong';
    if (answer === '\uB300\uCCB4\uB85C \uB9DE\uC74C') return 'goodSoft';
  }
  if ((questionId === 'instance' || questionId === 'mask_quality') && answer === '\uC2E4\uD328') {
    return 'badStrong';
  }
  if ((questionId === 'instance' || questionId === 'mask_quality') && answer === '\uBD80\uC815\uD655') {
    return 'bad';
  }
  return category;
}

function severityFor(questionId: string, answer: string) {
  const category = categoryFor(questionId, answer);
  if (category === 'bad') return 2;
  if (category === 'warning' || category === 'uncertain' || category === 'other') return 1;
  return 0;
}

function isReviewableNode(nodeId: string) {
  return humanLabel(nodeId).toLowerCase() !== 'others';
}

function nodeDepth(nodeId: string) {
  return Math.max(String(nodeId || '').split('__').filter(Boolean).length - 1, 0);
}

function isLeafFromManifest(manifestByImage, imageId: string, nodeId: string) {
  const node = manifestByImage?.[imageId]?.nodes?.[nodeId];
  if (node && Array.isArray(node.children)) return node.children.length === 0;
  return true;
}

function increment(map, key: string, amount = 1) {
  map[key] = (map[key] || 0) + amount;
}

function breakdownFromCounts(counts, questionId: string, total: number) {
  return Object.entries(counts || {})
    .map(([answer, count]) => {
      const category = categoryFor(questionId, answer);
      return {
        answer,
        count,
        ratio: total ? count / total : 0,
        category,
        tone: toneFor(questionId, answer, category),
      };
    })
    .sort((a, b) => b.count - a.count || String(a.answer).localeCompare(String(b.answer)));
}

async function loadManifestRows(imageIds: string[]) {
  if (!imageIds.length) return [];
  const supabase = getSupabaseAdmin();
  const rows = [];
  for (const ids of chunk([...new Set(imageIds)], 150)) {
    const { data, error } = await supabase
      .from(getManifestTableName())
      .select('image_id, actual_nodes, nodes')
      .in('image_id', ids);
    if (error) throw error;
    rows.push(...(data || []));
  }
  return rows;
}

function emptyQuestionStats() {
  return Object.fromEntries(
    QUESTION_DEFS.map((question) => [
      question.id,
      {
        ...question,
        answered: 0,
        targetCoverage: 0,
        answeredNodeCoverage: 0,
        values: {},
        breakdown: [],
      },
    ]),
  );
}

function emptyTreeQuestionStats() {
  return Object.fromEntries(
    TREE_QUESTION_DEFS.map((question) => [
      question.id,
      {
        ...question,
        answered: 0,
        imageCoverage: 0,
        values: {},
        breakdown: [],
      },
    ]),
  );
}

export async function loadAdminAnalytics() {
  const supabase = getSupabaseAdmin();
  const expectedUsers = reviewerIds();

  const [{ data: reviewRows, error: reviewError }, { data: assignmentRows, error: assignmentError }] = await Promise.all([
    supabase
      .from(getReviewTableName())
      .select('reviewer_id, payload, updated_at'),
    supabase
      .from(getAssignmentsTableName())
      .select('reviewer_id, image_id, sort_index')
      .in('reviewer_id', expectedUsers)
      .order('reviewer_id')
      .order('sort_index'),
  ]);

  if (reviewError) throw reviewError;
  if (assignmentError) throw assignmentError;

  const assignedImageIds = [...new Set((assignmentRows || []).map((row) => String(row.image_id)))];
  const manifestRows = await loadManifestRows(assignedImageIds);
  const manifestByImage = Object.fromEntries((manifestRows || []).map((row) => [String(row.image_id), row]));

  const assignmentsByUser = Object.fromEntries(expectedUsers.map((id) => [id, []]));
  for (const row of assignmentRows || []) {
    const reviewerId = String(row.reviewer_id);
    if (assignmentsByUser[reviewerId]) assignmentsByUser[reviewerId].push(String(row.image_id));
  }

  const targetNodeIdsByUserImage = {};
  const targetCountsByUser = Object.fromEntries(expectedUsers.map((id) => [id, 0]));
  for (const reviewerId of expectedUsers) {
    for (const imageId of assignmentsByUser[reviewerId] || []) {
      const actualNodes = manifestByImage[imageId]?.actual_nodes || [];
      const targetNodes = (Array.isArray(actualNodes) ? actualNodes : []).filter(isReviewableNode);
      targetNodeIdsByUserImage[`${reviewerId}:${imageId}`] = new Set(targetNodes);
      targetCountsByUser[reviewerId] += targetNodes.length;
    }
  }

  const presentUsers = new Set((reviewRows || []).map((row) => String(row.reviewer_id)).filter(isTargetReviewer));
  const userStats = Object.fromEntries(expectedUsers.map((reviewerId) => [
    reviewerId,
    {
      reviewerId,
      present: presentUsers.has(reviewerId),
      targetImages: assignmentsByUser[reviewerId]?.length || 0,
      targetNodes: targetCountsByUser[reviewerId] || 0,
      answeredNodes: 0,
      leafAnswered: 0,
      nonLeafAnswered: 0,
      badNodes: 0,
      nonidealNodes: 0,
      issueScore: 0,
      treeSummariesAnswered: 0,
      treeBadAnswers: 0,
      treeNonidealAnswers: 0,
      firstUpdatedAt: '',
      lastUpdatedAt: '',
      questionStats: emptyQuestionStats(),
      treeQuestionStats: emptyTreeQuestionStats(),
    },
  ]));

  const overallQuestionCounts = Object.fromEntries(QUESTION_DEFS.map((q) => [q.id, {}]));
  const overallTreeQuestionCounts = Object.fromEntries(TREE_QUESTION_DEFS.map((q) => [q.id, {}]));
  const leafQuestionCounts = {};
  for (const q of QUESTION_DEFS) {
    leafQuestionCounts[`${q.id}:leaf`] = {};
    leafQuestionCounts[`${q.id}:nonleaf`] = {};
  }

  const labelCounts = {};
  const imageCounts = {};
  const timelineCounts = {};
  let totalIssueScore = 0;

  for (const row of reviewRows || []) {
    const reviewerId = String(row.reviewer_id || '');
    if (!isTargetReviewer(reviewerId)) continue;

    const stat = userStats[reviewerId];
    const payload = row.payload && typeof row.payload === 'object' ? row.payload : {};

    for (const [imageId, imagePayload] of Object.entries(payload || {})) {
      const nodes = imagePayload?.nodes || {};
      const treeSummary = imagePayload?.tree_summary || {};
      const treeAnswersRaw = treeSummary?.answers || {};
      const treeAnswers = {};
      for (const [key, value] of Object.entries(treeAnswersRaw || {})) {
        if (hasAnswer(value)) treeAnswers[key] = normalizeAnswer(value);
      }
      if (Object.keys(treeAnswers).length) {
        const treeUpdatedAt = treeSummary?.updated_at ? String(treeSummary.updated_at) : '';
        if (treeUpdatedAt) {
          if (!stat.firstUpdatedAt || treeUpdatedAt < stat.firstUpdatedAt) stat.firstUpdatedAt = treeUpdatedAt;
          if (!stat.lastUpdatedAt || treeUpdatedAt > stat.lastUpdatedAt) stat.lastUpdatedAt = treeUpdatedAt;
        }
        for (const q of TREE_QUESTION_DEFS) {
          const answer = treeAnswers[q.id];
          if (!answer) continue;
          const category = categoryFor(q.id, answer);
          const treeQ = stat.treeQuestionStats[q.id];
          treeQ.answered += 1;
          increment(treeQ.values, answer);
          increment(overallTreeQuestionCounts[q.id], answer);
          stat.treeSummariesAnswered += 1;
          if (category === 'bad') stat.treeBadAnswers += 1;
          if (category !== 'good') stat.treeNonidealAnswers += 1;
        }
      }

      if (!nodes || typeof nodes !== 'object') continue;

      for (const [nodeId, nodePayload] of Object.entries(nodes)) {
        const answersRaw = nodePayload?.answers || {};
        const answers = {};
        for (const [key, value] of Object.entries(answersRaw || {})) {
          if (hasAnswer(value)) answers[key] = normalizeAnswer(value);
        }
        if (!Object.keys(answers).length) continue;

        const leaf = isLeafFromManifest(manifestByImage, String(imageId), String(nodeId));
        const label = humanLabel(String(nodeId));
        const updatedAt = nodePayload?.updated_at ? String(nodePayload.updated_at) : '';
        const nodeQuestions = QUESTION_DEFS.filter((q) => answers[q.id]);
        let nodeBad = false;
        let nodeNonideal = false;
        let nodeIssueScore = 0;

        stat.answeredNodes += 1;
        if (leaf) stat.leafAnswered += 1;
        else stat.nonLeafAnswered += 1;

        if (updatedAt) {
          if (!stat.firstUpdatedAt || updatedAt < stat.firstUpdatedAt) stat.firstUpdatedAt = updatedAt;
          if (!stat.lastUpdatedAt || updatedAt > stat.lastUpdatedAt) stat.lastUpdatedAt = updatedAt;
          const day = updatedAt.slice(0, 10);
          increment(timelineCounts, `${day}:ALL`);
          increment(timelineCounts, `${day}:${reviewerId}`);
        }

        imageCounts[String(imageId)] ||= {
          imageId: String(imageId),
          responses: 0,
          badNodes: 0,
          nonidealNodes: 0,
          issueScore: 0,
        };
        imageCounts[String(imageId)].responses += 1;

        labelCounts[label] ||= {
          label,
          responses: 0,
          badNodes: 0,
          nonidealNodes: 0,
          issueScore: 0,
        };
        labelCounts[label].responses += 1;

        for (const q of nodeQuestions) {
          const answer = answers[q.id];
          const severity = severityFor(q.id, answer);
          const category = categoryFor(q.id, answer);
          const userQ = stat.questionStats[q.id];
          userQ.answered += 1;
          increment(userQ.values, answer);
          increment(overallQuestionCounts[q.id], answer);
          increment(leafQuestionCounts[`${q.id}:${leaf ? 'leaf' : 'nonleaf'}`], answer);
          nodeIssueScore += severity;
          if (category === 'bad') nodeBad = true;
          if (category !== 'good') nodeNonideal = true;
        }

        if (nodeBad) {
          stat.badNodes += 1;
          imageCounts[String(imageId)].badNodes += 1;
          labelCounts[label].badNodes += 1;
        }
        if (nodeNonideal) {
          stat.nonidealNodes += 1;
          imageCounts[String(imageId)].nonidealNodes += 1;
          labelCounts[label].nonidealNodes += 1;
        }
        stat.issueScore += nodeIssueScore;
        imageCounts[String(imageId)].issueScore += nodeIssueScore;
        labelCounts[label].issueScore += nodeIssueScore;
        totalIssueScore += nodeIssueScore;
      }
    }
  }

  for (const stat of Object.values(userStats)) {
    stat.completionRate = stat.targetNodes ? stat.answeredNodes / stat.targetNodes : 0;
    stat.badRate = stat.answeredNodes ? stat.badNodes / stat.answeredNodes : 0;
    stat.nonidealRate = stat.answeredNodes ? stat.nonidealNodes / stat.answeredNodes : 0;
    stat.avgIssueScore = stat.answeredNodes ? stat.issueScore / stat.answeredNodes : 0;
    stat.treeBadRate = stat.treeSummariesAnswered ? stat.treeBadAnswers / stat.treeSummariesAnswered : 0;
    stat.treeNonidealRate = stat.treeSummariesAnswered ? stat.treeNonidealAnswers / stat.treeSummariesAnswered : 0;
    stat.questionStats = QUESTION_DEFS.map((q) => {
      const item = stat.questionStats[q.id];
      item.targetCoverage = stat.targetNodes ? item.answered / stat.targetNodes : 0;
      item.answeredNodeCoverage = stat.answeredNodes ? item.answered / stat.answeredNodes : 0;
      item.breakdown = breakdownFromCounts(item.values, q.id, item.answered);
      return item;
    });
    stat.treeQuestionStats = TREE_QUESTION_DEFS.map((q) => {
      const item = stat.treeQuestionStats[q.id];
      item.imageCoverage = stat.targetImages ? item.answered / stat.targetImages : 0;
      item.breakdown = breakdownFromCounts(item.values, q.id, item.answered);
      return item;
    }).filter((q) => q.answered > 0 || q.id === 'overall_consistency' || q.id === 'missing_critical_nodes');
  }

  const questionOverall = QUESTION_DEFS.map((q) => {
    const total = Object.values(overallQuestionCounts[q.id]).reduce((sum, count) => sum + count, 0);
    return {
      ...q,
      total,
      breakdown: breakdownFromCounts(overallQuestionCounts[q.id], q.id, total),
      leafBreakdown: breakdownFromCounts(leafQuestionCounts[`${q.id}:leaf`], q.id, Object.values(leafQuestionCounts[`${q.id}:leaf`]).reduce((sum, count) => sum + count, 0)),
      nonLeafBreakdown: breakdownFromCounts(leafQuestionCounts[`${q.id}:nonleaf`], q.id, Object.values(leafQuestionCounts[`${q.id}:nonleaf`]).reduce((sum, count) => sum + count, 0)),
    };
  }).filter((q) => q.total > 0);

  const treeQuestionOverall = TREE_QUESTION_DEFS.map((q) => {
    const total = Object.values(overallTreeQuestionCounts[q.id]).reduce((sum, count) => sum + count, 0);
    return {
      ...q,
      total,
      breakdown: breakdownFromCounts(overallTreeQuestionCounts[q.id], q.id, total),
    };
  }).filter((q) => q.total > 0);

  const users = expectedUsers.map((id) => userStats[id]);
  const totalTargetNodes = users.reduce((sum, row) => sum + row.targetNodes, 0);
  const totalAnsweredNodes = users.reduce((sum, row) => sum + row.answeredNodes, 0);
  const totalBadNodes = users.reduce((sum, row) => sum + row.badNodes, 0);
  const totalNonidealNodes = users.reduce((sum, row) => sum + row.nonidealNodes, 0);
  const totalTreeAnswers = users.reduce((sum, row) => sum + row.treeSummariesAnswered, 0);
  const totalTreeBadAnswers = users.reduce((sum, row) => sum + row.treeBadAnswers, 0);
  const totalTreeNonidealAnswers = users.reduce((sum, row) => sum + row.treeNonidealAnswers, 0);

  return {
    generatedAt: new Date().toISOString(),
    users,
    questionOverall,
    treeQuestionOverall,
    topLabels: Object.values(labelCounts)
      .map((row) => ({
        ...row,
        badRate: row.responses ? row.badNodes / row.responses : 0,
        nonidealRate: row.responses ? row.nonidealNodes / row.responses : 0,
        avgIssueScore: row.responses ? row.issueScore / row.responses : 0,
      }))
      .filter((row) => row.responses >= 10)
      .sort((a, b) => b.badRate - a.badRate || b.responses - a.responses)
      .slice(0, 18),
    topImages: Object.values(imageCounts)
      .map((row) => ({
        ...row,
        badRate: row.responses ? row.badNodes / row.responses : 0,
        nonidealRate: row.responses ? row.nonidealNodes / row.responses : 0,
        avgIssueScore: row.responses ? row.issueScore / row.responses : 0,
      }))
      .filter((row) => row.responses >= 10)
      .sort((a, b) => b.badRate - a.badRate || b.responses - a.responses)
      .slice(0, 18),
    timeline: Object.entries(timelineCounts)
      .map(([key, count]) => {
        const [date, reviewerId] = key.split(':');
        return { date, reviewerId, count };
      })
      .sort((a, b) => a.date.localeCompare(b.date) || a.reviewerId.localeCompare(b.reviewerId)),
    summary: {
      presentUsers: users.filter((row) => row.present).length,
      assignedUsers: users.filter((row) => row.targetImages > 0).length,
      completedUsers: users.filter((row) => row.targetNodes > 0 && row.completionRate >= 1).length,
      totalTargetNodes,
      totalAnsweredNodes,
      completionRate: totalTargetNodes ? totalAnsweredNodes / totalTargetNodes : 0,
      totalBadNodes,
      badRate: totalAnsweredNodes ? totalBadNodes / totalAnsweredNodes : 0,
      totalNonidealNodes,
      nonidealRate: totalAnsweredNodes ? totalNonidealNodes / totalAnsweredNodes : 0,
      avgIssueScore: totalAnsweredNodes ? totalIssueScore / totalAnsweredNodes : 0,
      totalTreeAnswers,
      totalTreeBadAnswers,
      treeBadRate: totalTreeAnswers ? totalTreeBadAnswers / totalTreeAnswers : 0,
      totalTreeNonidealAnswers,
      treeNonidealRate: totalTreeAnswers ? totalTreeNonidealAnswers / totalTreeAnswers : 0,
    },
  };
}
