// @ts-nocheck
'use client';

import {
  getAnswersBucket,
  nodeQuestionsFor,
  treeQuestionsFor,
} from '../lib/review-logic';
import { answerOptionLabel, uiText } from '../lib/i18n';

function SingleChoiceQuestion({ question, value, onChange, language }) {
  return (
    <div className="questionCard">
      <div className="questionLabel">{question.label}</div>
      <div className="choiceRow">
        {question.options.map((option) => {
          const optionLabel = answerOptionLabel(option, language);
          return (
            <label className="choiceChip" key={option}>
              <input
                type="radio"
                name={question.id}
                checked={value === option}
                onChange={() => onChange(option)}
                aria-label={optionLabel}
              />
              <span>{optionLabel}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function MultiChoiceQuestion({ question, value, onChange, language }) {
  const selected = Array.isArray(value) ? value : [];

  function toggle(option) {
    const next = selected.includes(option)
      ? selected.filter((item) => item !== option)
      : [...selected, option];
    onChange(next);
  }

  return (
    <div className="questionCard">
      <div className="questionLabel">{question.label}</div>
      <div className="choiceRow">
        {question.options.map((option) => {
          const optionLabel = answerOptionLabel(option, language);
          return (
            <label className="choiceChip" key={option}>
              <input
                type="checkbox"
                checked={selected.includes(option)}
                onChange={() => toggle(option)}
                aria-label={optionLabel}
              />
              <span>{optionLabel}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function TextQuestion({ question, value, onChange }) {
  return (
    <div className="questionCard isWide">
      <div className="questionLabel">{question.label}</div>
      <textarea
        className="questionTextarea"
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
      />
    </div>
  );
}

export default function QuestionPanel({
  record,
  annotations,
  imageId,
  mode,
  nodeId,
  onAnswerChange,
  translationMap,
  language,
}) {
  const questions = mode === 'tree'
    ? treeQuestionsFor(language)
    : nodeQuestionsFor(record, nodeId, { language, translationMap });
  const answers = getAnswersBucket(annotations, imageId, mode, nodeId)?.answers || {};

  const headerTitle = mode === 'tree'
    ? uiText(language, 'questions.treeTitle')
    : uiText(language, 'questions.nodeTitle');

  return (
    <section className="sectionCard">
      <div className="sectionHeaderWithMeta">
        <div>
          <h2 className="sectionTitle">{headerTitle}</h2>
          {/* <div className="statusPillsRow">
            {pills.map((pill) => (
              <span className="statusPill" key={pill}>{pill}</span>
            ))}
          </div> */}
        </div>
      </div>

      <div className="questionsGrid">
        {questions.map((question) => {
          const value = answers[question.id];
          const onChange = (nextValue) => onAnswerChange(mode, question.id, nextValue, nodeId);

          if (question.type === 'single_choice') {
            return (
              <SingleChoiceQuestion
                key={question.id}
                question={question}
                value={value}
                onChange={onChange}
                language={language}
              />
            );
          }
          if (question.type === 'multi_choice') {
            return (
              <MultiChoiceQuestion
                key={question.id}
                question={question}
                value={value}
                onChange={onChange}
                language={language}
              />
            );
          }
          return <TextQuestion key={question.id} question={question} value={value} onChange={onChange} />;
        })}
      </div>
    </section>
  );
}
