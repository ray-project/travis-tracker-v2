import { graphql, PageProps } from "gatsby";
import React, { useState } from "react";
import { Button } from "antd";

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
  const [showAll, setShowAll] = useState<boolean>(false);
  const numHidden = displayData.failed_tests.length - 100;
  return (
    <LayoutWrapper>
      <Title></Title>

      <StatsPane stats={displayData.stats}></StatsPane>

      {showAll
        ? displayData.failed_tests.map((c) => (
            <TestCase case={c}></TestCase>
          ))
        : displayData.failed_tests
            .slice(0, 100)
            .map((c) => (
              <TestCase case={c}></TestCase>
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
