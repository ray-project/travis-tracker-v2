import { PageProps } from "gatsby";
import React from "react";
import { Alert, Col, Row, Table, Tag, Typography } from "antd";

import LayoutWrapper from "../components/layout";
import { SiteNightlyRoot, SiteNightlyRun } from "../interface";
import rawData from "../nightly.json";

const nightlyData = rawData as SiteNightlyRoot;

const GITHUB_COMMIT = "https://github.com/ray-project/ray/commit";

// A run that never produced test jobs (aborted at init, cancelled) must not be
// rendered as a pass — it carries no signal about the wheel either way.
const isIncomplete = (run: SiteNightlyRun) =>
  run.tests_total === 0 || run.state === "canceled";

const ResultTag: React.FC<{ run: SiteNightlyRun }> = ({ run }) => {
  if (isIncomplete(run)) {
    return <Tag color="default">INCOMPLETE</Tag>;
  }
  if (run.tests_failed === 0) {
    return <Tag color="green">ALL {run.tests_total} PASSED</Tag>;
  }
  // Most red nights are a couple of flaky tests; a handful are real breakage.
  // Colouring by magnitude keeps those two cases visually distinct.
  const color = run.tests_failed > 10 ? "red" : "orange";
  return (
    <Tag color={color}>
      {run.tests_failed} of {run.tests_total} FAILED
    </Tag>
  );
};

const App: React.FC<PageProps> = () => {
  const runs = nightlyData.runs;

  const generated = new Date(nightlyData.generated_at);
  const hoursOld = (Date.now() - generated.getTime()) / 36e5;

  const columns = [
    {
      title: "Date",
      dataIndex: "created_at",
      render: (value: string) => value.slice(0, 10),
    },
    {
      title: "Commit",
      dataIndex: "commit",
      render: (commit: string, run: SiteNightlyRun) => (
        <a href={`${GITHUB_COMMIT}/${commit}`} target="_blank" rel="noreferrer">
          <code>{run.commit_short}</code>
        </a>
      ),
    },
    {
      title: "Result",
      key: "result",
      render: (_: unknown, run: SiteNightlyRun) => <ResultTag run={run} />,
    },
    {
      title: "Nightly wheel",
      dataIndex: "wheel_base",
      render: (wheelBase: string) =>
        wheelBase ? (
          <a href={wheelBase} target="_blank" rel="noreferrer">
            wheels
          </a>
        ) : null,
    },
  ];

  return (
    <LayoutWrapper>
      <Row justify="space-around" align="middle">
        <Col flex="auto">
          <Typography.Title level={1}>
            Ray Nightly Release Test Status
          </Typography.Title>
        </Col>
      </Row>

      <Alert
        type="info"
        showIcon
        message="How to read this page"
        description={
          <>
            Each row is one scheduled run of Ray's release tests against a
            master commit, and the wheel built from that commit. A run covers
            roughly 265 release tests. Most failing nights are one or two
            flaky or infrastructure-related tests rather than a broken wheel, so
            check the failure count and the test names before drawing a
            conclusion. Expand a row to see exactly which tests failed.
          </>
        }
        style={{ marginBottom: "1rem" }}
      />

      {hoursOld > 12 && (
        <Alert
          type="warning"
          showIcon
          message={`This data is ${Math.floor(
            hoursOld
          )} hours old — the refresh job may be failing.`}
          style={{ marginBottom: "1rem" }}
        />
      )}

      <Table
        dataSource={runs}
        columns={columns}
        rowKey={(run) => String(run.build_number)}
        pagination={{ pageSize: 30 }}
        expandable={{
          rowExpandable: (run) => run.failed_tests.length > 0,
          expandedRowRender: (run) => (
            <ul>
              {run.failed_tests.map((name) => (
                <li key={name}>
                  <code>{name}</code>
                </li>
              ))}
            </ul>
          ),
        }}
      />

      <Typography.Paragraph type="secondary">
        Last updated {nightlyData.generated_at}.
      </Typography.Paragraph>
    </LayoutWrapper>
  );
};

export default App;
