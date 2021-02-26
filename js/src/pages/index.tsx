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
  const [showFlaky, setShowFlaky] = useState<boolean>(false);
  const numHidden = displayData.flaky_tests.length - 20;
  return (
    <LayoutWrapper>
      <Title></Title>

      <StatsPane stats={displayData.stats}></StatsPane>

      {displayData.failed_tests.map((c) => (
        <TestCase case={c} segmentBarColorType={"failed"}></TestCase>
      ))}

      {showFlaky
        ? displayData.flaky_tests.map((c) => (
            <TestCase case={c} segmentBarColorType={"flaky"}></TestCase>
          ))
        : displayData.flaky_tests
            .slice(0, 20)
            .map((c) => (
              <TestCase case={c} segmentBarColorType={"flaky"}></TestCase>
            ))}

      {numHidden > 0 && (
        <Button
          style={{ margin: "12px" }}
          type={"primary"}
          onClick={() => {
            setShowFlaky((val) => !val);
          }}
        >
          {showFlaky
            ? "Hide additional tests"
            : `Show all flaky tests (${numHidden} hidden, it will take ~2s to load) `}
        </Button>
      )}

      <BuildTimeFooter
        buildTime={Date.parse(data.site.buildTime)}
      ></BuildTimeFooter>
    </LayoutWrapper>
  );
};

export default App;
