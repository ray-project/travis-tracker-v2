import { graphql, PageProps } from "gatsby";
import React, { useState } from "react";
import { Button, Radio, Table } from "antd";
import { QueryStateOpts, useQueryState } from "use-location-state";

import LayoutWrapper from "../components/layout";
import BuildTimeFooter from "../components/time";
import Title from "../components/title";
import TestCase from "../components/case";
import StatsPane from "../components/stat";
import { SiteDisplayRoot } from "../interface";
import rawData from "../data.json";

const displayData = rawData as SiteDisplayRoot;

export const query = graphql`
  {
    site {
      buildTime
    }
  }
`;

type DataProps = {
  site: {
    buildTime: string;
  };
};

const App: React.FC<PageProps<DataProps>> = ({ data }) => {
  const [showAll, setShowAll] = useQueryState<boolean>("showAll", false);
  const [compactMode, setCompactMode] = useQueryState<boolean>(
    "compactMode",
    false
  );
  const [ownerSelection, setOwnerSelection] = useQueryState<string>(
    "owner",
    "all"
  );
  const [sortByRuntime, setSortByRuntime] = useQueryState<boolean>(
    "sortByRuntime",
    false
  );

  const { dataSource, columns } = JSON.parse(displayData.table_stat);
  const numHidden = displayData.failed_tests.length - 100;

  let testsToDisplay = displayData.failed_tests;
  testsToDisplay = testsToDisplay.filter(
    (c) => ownerSelection === "all" || ownerSelection === c.owner
  );
  if (sortByRuntime) {
    // compare by p50
    testsToDisplay = testsToDisplay.sort(
      (a, b) => b.build_time_stats[1] - a.build_time_stats[1]
    );
  } else if (!showAll) {
    testsToDisplay = testsToDisplay.slice(0, 100);
  }

  return (
    <LayoutWrapper>
      <Title></Title>

      <StatsPane stats={displayData.stats}></StatsPane>

      <Table
        dataSource={dataSource}
        columns={columns}
        size={"small"}
        pagination={false}
      ></Table>

      <Radio.Group
        onChange={(e) => setOwnerSelection(e.target.value)}
        defaultValue={ownerSelection}
      >
        <Radio.Button value="all">team:all</Radio.Button>
        {displayData.test_owners.map((owner) => (
          <Radio.Button value={owner}>{owner}</Radio.Button>
        ))}
      </Radio.Group>

      <Button
        style={{ margin: "12px" }}
        type={"default"}
        onClick={() => setCompactMode((val) => !val)}
      >
        Toggle Compact Mode
      </Button>
      <Button
        style={{ margin: "12px" }}
        type={"default"}
        onClick={() => setSortByRuntime((val) => !val)}
      >
        Toggle Sort by Runtime
      </Button>

      {testsToDisplay.map((c) => (
        <TestCase case={c} compact={compactMode}></TestCase>
      ))}

      {numHidden > 0 && (
        <Button
          style={{ margin: "12px" }}
          type={"primary"}
          onClick={() => {
            setShowAll((val) => !val);
          }}
        >
          {showAll
            ? "Hide additional tests"
            : `Show all failed tests (${numHidden} hidden, it will take ~2s to load) `}
        </Button>
      )}

      <BuildTimeFooter
        buildTime={Date.parse(data.site.buildTime)}
      ></BuildTimeFooter>
    </LayoutWrapper>
  );
};

export default App;
