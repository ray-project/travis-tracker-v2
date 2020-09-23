import { graphql, PageProps } from "gatsby";
import React from "react";

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

const App: React.FC<PageProps<DataProps>> = ({ data }) => (
  <LayoutWrapper>
    <Title></Title>

    <StatsPane stats={displayData.stats}></StatsPane>

    {displayData.failed_tests.map((c) => (
      <TestCase case={c}></TestCase>
    ))}

    <BuildTimeFooter
      buildTime={Date.parse(data.site.buildTime)}
    ></BuildTimeFooter>
  </LayoutWrapper>
);

export default App;
