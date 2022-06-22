import { graphql, Link, PageProps } from "gatsby";
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

const App: React.FC<PageProps<DataProps>> = ({ data, location }) => {
  const [showAll, setShowAll] = useQueryState<boolean>("showAll", false);
  const ownerSelection = new URLSearchParams(location.search).get("owner") || "all";

  const { dataSource, columns } = JSON.parse(displayData.table_stat);
  const numHidden = displayData.failed_tests.length - 100;

  let testsToDisplay = displayData.failed_tests;
  testsToDisplay = testsToDisplay.filter(
    (c) => ownerSelection === "all" || ownerSelection === c.owner
  );

  if (!showAll) {
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
        style={{paddingTop: "1%"}}
        defaultValue={ownerSelection}
      >
        <Radio.Button value="all"><Link to={"/?owner=all"}>team:all</Link></Radio.Button>
        {displayData.test_owners.map((owner) => (
          <Radio.Button value={owner}>
            <Link to={"/?owner="+owner}>{owner}</Link></Radio.Button>
        ))}
      </Radio.Group>


      {testsToDisplay.map((c) => (
        <TestCase case={c} compact={false}></TestCase>
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
