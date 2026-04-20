// @ts-nocheck

import { humanLabel, nowIso } from './utils';

export const TREE_SUMMARY_NODE_ID = '__tree_summary__';

export const TREE_BUTTON_MIN_WIDTH_PX = 10;
export const TREE_BUTTON_MAX_WIDTH_PX = 320;
export const TREE_BUTTON_BASE_PX = 10;
export const TREE_CHAR_WIDTH_PX = 9;
export const TREE_BUTTON_HEIGHT_PX = 32;
export const TREE_CONNECTOR_STUB_PX = 8;
export const TREE_CONNECTOR_RADIUS_PX = 8;
export const TREE_SIBLING_GAP_PX = 10;
export const TREE_ROOT_GAP_PX =0;
export const TREE_SIDE_PAD_PX = 10;
export const TREE_ROW_HEIGHT_PX = 50;
export const TREE_ROW_GAP_PX = 24;
export const TREE_PANEL_TOP_PAD_PX = 12;

const NODE_QUESTION_AUTOFILL_ON_LABEL_REJECT = {
  mask_missing: '판단불가',
  mask_extra: '판단불가',
  instance: '판단불가',
  mask_quality: '판단불가',
  decomposition: '판단불가',
  missing_child: '판단불가',
};

export function translatedLabel(imageId, nodeId, translationMap) {
  if (!nodeId) return '-';
  const base = humanLabel(nodeId);
  const entry = translationMap?.[String(imageId)]?.[String(nodeId)];
  if (!entry) return base;

  const ko = String(entry.ko || '').trim();
  const en = String(entry.en || '').trim();
  if (ko && ko !== '전체 장면' && ko.toLowerCase() !== en.toLowerCase()) {
    return `${base} (${ko})`;
  }
  return base;
}

export function translatedPathLabels(imageId, nodeId, translationMap) {
  const parts = String(nodeId || '').split('__');
  const built = [];
  const acc = [];

  for (const part of parts) {
    acc.push(part);
    built.push(translatedLabel(imageId, acc.join('__'), translationMap));
  }

  return built;
}

export function getNodeDepth(nodeId) {
  const parts = String(nodeId || '').split('__').filter(Boolean);
  return parts.filter((part, index) => index > 0 && part.toLowerCase() !== 'others').length;
}

export function isReviewableNode(nodeId) {
  return humanLabel(nodeId).toLowerCase() !== 'others';
}

export function firstReviewableNodeId(record) {
  for (const nodeId of record?.actual_nodes || []) {
    if (isReviewableNode(nodeId)) return nodeId;
  }
  return null;
}

export function treeDisplayChildren(record, nodeId) {
  if (!record?.nodes?.[nodeId]) return [];
  return record.nodes[nodeId].children || [];
}

export function displayRootIds(record) {
  const roots = [...(record?.roots || [])];
  if (!roots.length) return [TREE_SUMMARY_NODE_ID];
  return roots;
}

export function nodeQuestionsFor(record, nodeId) {
  const currentLabel = humanLabel(nodeId).replace(/_/g, ' ');
  const childIds = record?.nodes?.[nodeId]?.children || [];
  const hasChildren = childIds.length > 0;

  return [
    {
      id: 'label',
      label: `Q1. 마스크가 가리키는 영역에 <${currentLabel}>이(가) 존재하나요?`,
      type: 'single_choice',
      options: ['예', '아니오', '판단불가'],
      required: true,
    },
    {
      id: 'mask_missing',
      label: `Q2. 마스크가 <${currentLabel}>에 해당하는 개체들을 전부 포함하고 있나요?`,
      type: 'single_choice',
      options: ['모두 포함함', '약간 놓침', '많이 놓침', '판단불가'],
      required: true,
    },
    {
      id: 'mask_extra',
      label: `Q3. 마스크가 <${currentLabel}> 외의 다른 개체를 포함하고 있나요?`,
      type: 'single_choice',
      options: ['포함하지 않음', '약간 포함', '많이 포함', '판단불가'],
      required: true,
    },
    {
      id: 'instance',
      label: `Q4. 마스크에서 <${currentLabel}>에 해당하는 영역만 보았을 때, 개별 인스턴스들이 서로 잘 구분되어 있나요?`,
      type: 'single_choice',
      options: ['정확', '수용 가능', '부정확', '실패', '판단불가'],
      required: true,
    },
    {
      id: 'mask_quality',
      label: `Q5. 마스크에서 <${currentLabel}>에 해당하는 영역만 보았을 때, 마스크의 윤곽과 모양이 보이는 영역을 잘 반영하고 있나요?`,
      type: 'single_choice',
      options: ['정확', '수용 가능', '부정확', '실패', '판단불가'],
      required: true,
    },
    {
      id: 'decomposition',
      label: hasChildren
        ? `Q6. <${currentLabel}>의 자식 중 하위 요소로 보기 어려운 항목이 있나요?`
        : `Q6. <${currentLabel}>를 여기서 더 세분화하지 않는 것이 적절한가요?`,
      type: 'single_choice',
      options: hasChildren
        ? ['없음', '조금 있음', '많이 있음', '판단불가']
        : ['예', '아니오', '판단불가'],
      required: true,
    },
    {
      id: 'missing_child',
      label: hasChildren
        ? `Q7. <${currentLabel}>의 자식으로 포함되었어야 할 중요한 하위 요소가 더 있나요?`
        : `Q7. <${currentLabel}>를 여기서 더 세분화하지 않는 것이 적절한가요?`,
      type: 'single_choice',
      options: hasChildren
        ? ['없음', '조금 있음', '많이 있음', '판단불가']
        : ['예', '아니오', '판단불가'],
      required: true,
    },
  ];
}

export function treeQuestionsFor() {
  return [
    {
      id: 'overall_consistency',
      label: '전체 트리가 이미지를 적절히 분해하였나요?',
      type: 'single_choice',
      options: ['맞음', '대체로 맞음', '부분적으로 맞음', '아님', '판단불가'],
      required: true,
    },
    {
      id: 'missing_critical_nodes',
      label: '남은 영역에 유의미한 요소가 있나요?',
      type: 'single_choice',
      options: ['없음', '조금 있음', '꽤 있음', '많음', '판단불가'],
      required: true,
    },
    {
      id: 'summary_comment',
      label: '추가 의견',
      type: 'text',
      required: false,
    },
  ];
}

export function ensureAnnotationBucket(annotations, imageId) {
  if (!annotations[imageId]) {
    annotations[imageId] = {
      nodes: {},
      tree_summary: { answers: {}, updated_at: null },
      image_review: { updated_at: null },
    };
  }
  return annotations[imageId];
}

export function ensureNodeBucket(annotations, imageId, nodeId) {
  const imageBucket = ensureAnnotationBucket(annotations, imageId);
  if (!imageBucket.nodes[nodeId]) {
    imageBucket.nodes[nodeId] = { answers: {}, updated_at: null };
  }
  return imageBucket.nodes[nodeId];
}

export function getAnswersBucket(annotations, imageId, mode, nodeId = null) {
  if (mode === 'node') {
    return ensureNodeBucket(annotations, imageId, nodeId || '');
  }
  return ensureAnnotationBucket(annotations, imageId).tree_summary;
}

export function requiredMissingQuestions(annotations, imageId, mode, questions, nodeId = null) {
  const answers = getAnswersBucket(annotations, imageId, mode, nodeId)?.answers || {};
  const missing = [];

  for (const q of questions) {
    if (!q.required) continue;
    const value = answers[q.id];
    if (q.type === 'multi_choice') {
      if (!value || !value.length) missing.push(q.id);
    } else if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) {
      missing.push(q.id);
    }
  }

  return missing;
}

export function nodeConfirmed(annotations, record, imageId, nodeId) {
  if (!isReviewableNode(nodeId)) return true;
  return requiredMissingQuestions(
    annotations,
    imageId,
    'node',
    nodeQuestionsFor(record, nodeId),
    nodeId,
  ).length === 0;
}

export function allNodesConfirmed(annotations, imageId, record) {
  const actualNodes = (record?.actual_nodes || []).filter((nodeId) => isReviewableNode(nodeId));
  return Boolean(actualNodes.length) && actualNodes.every((nodeId) => nodeConfirmed(annotations, record, imageId, nodeId));
}

export function treeSummaryConfirmed(annotations, imageId) {
  return requiredMissingQuestions(annotations, imageId, 'tree', treeQuestionsFor()).length === 0;
}

export function imageComplete(annotations, imageId, record) {
  return allNodesConfirmed(annotations, imageId, record) && treeSummaryConfirmed(annotations, imageId);
}

export function nodeProgress(annotations, imageId, record) {
  const actualNodes = (record?.actual_nodes || []).filter((nodeId) => isReviewableNode(nodeId));
  const done = actualNodes.filter((nodeId) => nodeConfirmed(annotations, record, imageId, nodeId)).length;
  return [done, actualNodes.length];
}

export function reviewProgress(annotations, imageId, record) {
  const [nodeDone, nodeTotal] = nodeProgress(annotations, imageId, record);
  const treeDone = treeSummaryConfirmed(annotations, imageId) ? 1 : 0;
  return [nodeDone + treeDone, nodeTotal + 1];
}

export function missingReport(annotations, imageId, record) {
  const missingNodes = [];

  for (const nodeId of record?.actual_nodes || []) {
    if (!isReviewableNode(nodeId)) continue;
    const missingQuestionIds = requiredMissingQuestions(
      annotations,
      imageId,
      'node',
      nodeQuestionsFor(record, nodeId),
      nodeId,
    );
    if (missingQuestionIds.length) {
      missingNodes.push({ node_id: nodeId, missing_question_ids: missingQuestionIds });
    }
  }

  const treeMissing = requiredMissingQuestions(annotations, imageId, 'tree', treeQuestionsFor());
  return { missing_nodes: missingNodes, tree_missing: treeMissing };
}

export function getInspectorPills(record, nodeId, translationMap) {
  const node = record?.nodes?.[nodeId];
  const imageId = record?.image_id;
  if (!node) {
    return ['현재: -', '부모: -', '자식: -', '깊이: -', '경로: -'];
  }

  const parentId = node.parent;
  const depth = getNodeDepth(nodeId);
  const children = (node.children || []).filter((childId) => {
    const childNode = record.nodes[childId];
    return !(childNode?.actual && !isReviewableNode(childId));
  });

  const currentText = translatedLabel(imageId, nodeId, translationMap);
  const parentText = parentId ? translatedLabel(imageId, parentId, translationMap) : '-';
  const childLabels = children.map((childId) => translatedLabel(imageId, childId, translationMap));
  const childrenText = childLabels.length ? childLabels.join(', ') : '-';
  const prettyPath = translatedPathLabels(imageId, nodeId, translationMap).join(' → ');

  return [
    `현재: ${currentText}`,
    `부모: ${parentText}`,
    `자식: ${childrenText}`,
    `깊이: ${depth}`,
    `경로: ${prettyPath}`,
  ];
}


export function nodeAssets(record, nodeId) {
  const node = record?.nodes?.[nodeId] || {};
  const bbox = node.bbox;
  const maskPath = node.mask_path || null;

  const replaceMaskSuffix = (path, nextSuffix) => {
    if (!path || typeof path !== 'string') return null;
    if (!path.endsWith('.mask.png')) return null;
    return path.replace(/\.mask\.png$/i, nextSuffix);
  };

  return {
    root_original: record?.root_image_path || null,
    instances_colored: node.instances_colored_path || replaceMaskSuffix(maskPath, '.instances.colored.png'),
    instance_paths: Array.isArray(node.instance_paths) ? node.instance_paths : [],
    full_size: record?.full_size || null,
    bbox: Array.isArray(bbox) ? bbox : bbox ? [bbox.x1, bbox.y1, bbox.x2, bbox.y2] : null,
  };

}

function hierarchyButtonWidthPx(nodeId) {
  const label = nodeId === TREE_SUMMARY_NODE_ID ? '전체트리' : humanLabel(nodeId);
  const width = TREE_BUTTON_BASE_PX + TREE_CHAR_WIDTH_PX * label.length;
  return Math.max(TREE_BUTTON_MIN_WIDTH_PX, Math.min(TREE_BUTTON_MAX_WIDTH_PX, width));
}

export function injectTreeSummaryNode(record) {
  const cloned = JSON.parse(JSON.stringify(record));
  if (!cloned.nodes[TREE_SUMMARY_NODE_ID]) {
    cloned.nodes[TREE_SUMMARY_NODE_ID] = {
      id: TREE_SUMMARY_NODE_ID,
      label: '전체트리',
      parent: null,
      children: [],
      actual: true,
    };
  }
  if (!(cloned.roots || []).includes(TREE_SUMMARY_NODE_ID)) {
    cloned.roots = [TREE_SUMMARY_NODE_ID, ...(cloned.roots || [])];
  }
  return cloned;
}

export function computeHierarchyLayout(record, opts = {}) {
  const {
    imageId,
    translationMap,
    getNodeLabel = (_imageId, nodeId) =>
      nodeId === TREE_SUMMARY_NODE_ID ? '전체트리' : humanLabel(nodeId),
    getNodeWidth,
  } = opts;

  const nodeWidths = {};
  const subtreeWidths = {};
  const nodeLefts = {};
  const rowsByDepth = {};

  function treeChildren(nodeId) {
    if (nodeId === TREE_SUMMARY_NODE_ID) return [];
    return record.nodes?.[nodeId]?.children || [];
  }

  function buttonWidth(nodeId) {
    if (typeof getNodeWidth === 'function') {
      return getNodeWidth(nodeId);
    }
    const label = getNodeLabel(imageId, nodeId, translationMap);
    const width = TREE_BUTTON_BASE_PX + TREE_CHAR_WIDTH_PX * String(label || '').length + 12;
    return Math.max(TREE_BUTTON_MIN_WIDTH_PX, Math.min(TREE_BUTTON_MAX_WIDTH_PX, width));
  }

  function displayRootIds() {
    const roots = Array.isArray(record.roots) ? [...record.roots] : [];
    return roots.length ? roots : [TREE_SUMMARY_NODE_ID];
  }

  function measure(nodeId) {
    const ownWidth = buttonWidth(nodeId);
    nodeWidths[nodeId] = ownWidth;

    const children = treeChildren(nodeId);
    if (!children.length) {
      subtreeWidths[nodeId] = ownWidth;
      return ownWidth;
    }

    let childrenTotal = 0;
    children.forEach((childId, idx) => {
      childrenTotal += measure(childId);
      if (idx < children.length - 1) {
        childrenTotal += TREE_SIBLING_GAP_PX;
      }
    });

    const subtreeWidth = Math.max(ownWidth, childrenTotal);
    subtreeWidths[nodeId] = subtreeWidth;
    return subtreeWidth;
  }

  function place(nodeId, leftX, depth) {
    nodeLefts[nodeId] = leftX + (subtreeWidths[nodeId] - nodeWidths[nodeId]) / 2;
    rowsByDepth[depth] ||= [];
    rowsByDepth[depth].push(nodeId);

    const children = treeChildren(nodeId);
    if (!children.length) return;

    if (children.length === 1) {
      const onlyChildId = children[0];
      const centeredChildLeft = leftX + (subtreeWidths[nodeId] - subtreeWidths[onlyChildId]) / 2;
      place(onlyChildId, centeredChildLeft, depth + 1);
      return;
    }

    let childLeft = leftX;
    children.forEach((childId, idx) => {
      place(childId, childLeft, depth + 1);
      childLeft += subtreeWidths[childId];
      if (idx < children.length - 1) {
        childLeft += TREE_SIBLING_GAP_PX;
      }
    });
  }

  const rootIds = displayRootIds();
  if (!rootIds.length) {
    return {
      rows: [],
      nodeLefts: {},
      nodeWidths: {},
      treeWidth: 0,
    };
  }

  let totalWidth = TREE_SIDE_PAD_PX * 2;
  rootIds.forEach((rootId, idx) => {
    totalWidth += measure(rootId);
    if (idx < rootIds.length - 1) {
      totalWidth += TREE_ROOT_GAP_PX;
    }
  });

  let leftX = TREE_SIDE_PAD_PX;
  rootIds.forEach((rootId, idx) => {
    place(rootId, leftX, 0);
    leftX += subtreeWidths[rootId];
    if (idx < rootIds.length - 1) {
      leftX += TREE_ROOT_GAP_PX;
    }
  });

  const rows = Object.keys(rowsByDepth)
    .map(Number)
    .sort((a, b) => a - b)
    .map((depth) => rowsByDepth[depth].sort((a, b) => nodeLefts[a] - nodeLefts[b]));

  return {rows, nodeLefts, nodeWidths, treeWidth: totalWidth,};
}

function roundedElbowPath(x1, y1, x2, y2, r) {
  if (Math.abs(x2 - x1) < 1) {
    return `M ${x1.toFixed(1)} ${y1.toFixed(1)} V ${y2.toFixed(1)}`;
  }

  const midY = (y1 + y2) / 2;
  const radius = Math.min(r, Math.abs(y2 - y1) / 2, Math.abs(x2 - x1) / 2);
  const dirX = x2 > x1 ? 1 : -1;

  return [
    `M ${x1.toFixed(1)} ${y1.toFixed(1)}`,
    `V ${(midY - radius).toFixed(1)}`,
    `Q ${x1.toFixed(1)} ${midY.toFixed(1)} ${(x1 + dirX * radius).toFixed(1)} ${midY.toFixed(1)}`,
    `H ${(x2 - dirX * radius).toFixed(1)}`,
    `Q ${x2.toFixed(1)} ${midY.toFixed(1)} ${x2.toFixed(1)} ${(midY + radius).toFixed(1)}`,
    `V ${y2.toFixed(1)}`,
  ].join(' ');
}

export function buildTreeConnectorPaths(record, layout, opts = {}) {
  const rows = layout.rows || [];
  const nodeLefts = layout.nodeLefts || {};
  const nodeWidths = layout.nodeWidths || {};
  const rowOffset = Number(opts?.rowOffset || 0);
  if (!rows.length) return [];

  function rowTopY(rowIdx) {
    return TREE_PANEL_TOP_PAD_PX + (rowIdx + rowOffset) * (TREE_ROW_HEIGHT_PX + TREE_ROW_GAP_PX);
  }

  function buttonTopY(rowIdx) {
    return rowTopY(rowIdx) + (TREE_ROW_HEIGHT_PX - TREE_BUTTON_HEIGHT_PX) / 2;
  }

  function buttonBottomY(rowIdx) {
    return buttonTopY(rowIdx) + TREE_BUTTON_HEIGHT_PX;
  }

  function nodeCenterX(nodeId) {
    return nodeLefts[nodeId] + nodeWidths[nodeId] / 2;
  }

  const paths = [];

  for (let rowIdx = 0; rowIdx < rows.length - 1; rowIdx += 1) {
    const parentRow = rows[rowIdx];
    const childRow = rows[rowIdx + 1];
    const childSet = new Set(childRow);
    const parentStubY = buttonBottomY(rowIdx) + TREE_CONNECTOR_STUB_PX;
    const childStubY = buttonTopY(rowIdx + 1) - TREE_CONNECTOR_STUB_PX;
    const busY = (parentStubY + childStubY) / 2;

    for (const parentId of parentRow) {
      const children = treeDisplayChildren(record, parentId).filter((childId) => childSet.has(childId));
      if (!children.length) continue;
      const px = nodeCenterX(parentId);

      paths.push(`M ${px.toFixed(1)} ${buttonBottomY(rowIdx).toFixed(1)} V ${parentStubY.toFixed(1)}`);

      if (children.length === 1) {
        const cx = nodeCenterX(children[0]);
        paths.push(roundedElbowPath(px, parentStubY, cx, childStubY, TREE_CONNECTOR_RADIUS_PX));
        paths.push(`M ${cx.toFixed(1)} ${childStubY.toFixed(1)} V ${buttonTopY(rowIdx + 1).toFixed(1)}`);
        continue;
      }

      const childCenters = children.map((childId) => nodeCenterX(childId));
      const leftX = Math.min(...childCenters);
      const rightX = Math.max(...childCenters);

      paths.push(`M ${px.toFixed(1)} ${parentStubY.toFixed(1)} V ${busY.toFixed(1)}`);
      paths.push(`M ${leftX.toFixed(1)} ${busY.toFixed(1)} H ${rightX.toFixed(1)}`);

      for (const cx of childCenters) {
        paths.push(roundedElbowPath(cx, busY, cx, childStubY, TREE_CONNECTOR_RADIUS_PX));
        paths.push(`M ${cx.toFixed(1)} ${childStubY.toFixed(1)} V ${buttonTopY(rowIdx + 1).toFixed(1)}`);
      }
    }
  }

  return paths;
}

export function applyAnswerChange(annotations, imageId, mode, questionId, value, nodeId = null) {
  const next = structuredClone(annotations || {});
  const bucket = getAnswersBucket(next, imageId, mode, nodeId);
  bucket.answers[questionId] = value;

  if (mode === 'node' && (questionId === 'decomposition' || questionId === 'missing_child')) {
    const mirroredQuestionId = questionId === 'decomposition' ? 'missing_child' : 'decomposition';
    const leafSharedValues = ['예', '아니오', '판단불가'];
    if (leafSharedValues.includes(value)) {
      bucket.answers[mirroredQuestionId] = value;
    }
  }

  if (mode === 'node' && questionId === 'label' && (value === '아니오' || value === '판단불가')) {
    Object.assign(bucket.answers, NODE_QUESTION_AUTOFILL_ON_LABEL_REJECT);
  }

  bucket.updated_at = nowIso();
  return next;
}

export { humanLabel } from "./utils";
